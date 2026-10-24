"""
Supplier assessments and the supplier portal: a supplier answers through a link with no
account, so the link's token is the only credential. It works for one assessment in one
organization, until it is submitted, cancelled, re-sent or expired, and it reaches nothing
else. Runs on both backends, like the security suite.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from libs.assessments import questions as aq
from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token, get_password_hash
from libs.common.store_assessments import portal_token_hash


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def portal(token: str) -> dict:
    return {"X-Portal-Token": token}


PASSWORD = "assessment-tests-pw-1"


def make_org(apps, client, roles=("admin", "viewer")) -> dict:
    """A fresh organization with one user per role (the shared demo organizations are left
    alone: other tests list every supplier in them)."""
    store = apps["gateway"].audit_store
    tag = uuid.uuid4().hex[:8]

    async def setup():
        org = await store.create_organization(f"Assessments {tag}")
        for role in roles:
            await store.create_user(org, f"{role}-{tag}@assess.example.com", role.title(),
                                    get_password_hash(PASSWORD), [role])
    asyncio.run(setup())
    tokens = {}
    for role in roles:
        response = client.post("/api/v1/auth/login", json={"email": f"{role}-{tag}@assess.example.com",
                                                            "password": PASSWORD})
        assert response.status_code == 200, response.text
        tokens[role] = response.json()
    return tokens


@pytest.fixture
def sarah(apps, client):
    """Admin of a fresh organization (named like the suite's usual admin)."""
    return make_org(apps, client, ("admin",))["admin"]


@pytest.fixture
def lisa(apps, client):
    """Admin of another fresh organization."""
    return make_org(apps, client, ("admin",))["admin"]


def org_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["org_id"]


def new_supplier(apps, org: str, name: str = "Orvane Fine Chemicals") -> str:
    store = apps["gateway"].audit_store
    supplier = asyncio.run(store.create_supplier(org, {"name": f"{name} {uuid.uuid4().hex[:4]}",
                                                      "supplier_code": f"AS-{uuid.uuid4().hex[:6]}",
                                                      "supplier_type": "manufacturer", "country_code": "DE"}))
    return str(supplier["id"])


def send(client, tokens, supplier_id, template="builtin:continuity", **extra):
    response = client.post("/api/v1/assessments", json={
        "supplier_id": supplier_id, "template_id": template, "recipient_email": "quality@supplier.example.com",
        "recipient_name": "Dana", "due_date": "2026-12-01", **extra}, headers=bearer(tokens["access_token"]))
    assert response.status_code == 200, response.text
    body = response.json()
    return body, body["portal_url"].split("#", 1)[1]


CONTINUITY_ANSWERS = {"bcp": "yes", "bcp_tested": "no", "single_site": "yes", "single_site_detail": "Tablets: one site",
                      "single_source": "no", "safety_stock_weeks": "6", "disruption": "no",
                      "subtier": [{"name": "Hexa API Ltd", "country": "in", "supplies": "Active ingredient"},
                                  {"name": "", "country": "", "supplies": ""}]}


class TestQuestions:
    def test_scores_come_from_the_good_answers_and_their_weights(self):
        questions = aq.BUILT_IN["builtin:continuity"]["questions"]
        answers, links = aq.clean_answers(questions, CONTINUITY_ANSWERS, final=True)
        assert answers["safety_stock_weeks"] == 6.0 and links == [
            {"name": "Hexa API Ltd", "country_code": "IN", "city": None, "supplies": "Active ingredient"}]
        score, flags = aq.score(questions, answers)
        # good: bcp 3, single_source 3, disruption 2 = 8 of 13 (bcp_tested 2 and single_site 3 flagged)
        assert score == round(100 * 8 / 13)
        assert [f["id"] for f in flags] == ["single_site", "bcp_tested"]

    def test_required_answers_are_needed_only_to_submit(self):
        questions = aq.BUILT_IN["builtin:quality"]["questions"]
        assert aq.clean_answers(questions, {"gmp": "yes"}, final=False)[0] == {"gmp": "yes"}
        with pytest.raises(ValueError, match="Outcome"):
            aq.clean_answers(questions, {"gmp": "yes", "recall": "no", "change_notice": "yes"}, final=True)

    @pytest.mark.parametrize("answers, message", [
        ({"bcp": "maybe"}, "yes or no"),
        ({"safety_stock_weeks": "lots"}, "number"),
        ({"subtier": [{"name": "X", "country": "India"}]}, "two-letter"),
        ({"subtier": [{"country": "IN"}]}, "name"),
    ])
    def test_bad_answers_are_refused(self, answers, message):
        with pytest.raises(ValueError, match=message):
            aq.clean_answers(aq.BUILT_IN["builtin:continuity"]["questions"], answers, final=False)

    def test_custom_questions_are_checked(self):
        with pytest.raises(ValueError, match="unique id"):
            aq.validate_questions([{"id": "a", "text": "x", "type": "text"}, {"id": "a", "text": "y", "type": "text"}])
        with pytest.raises(ValueError, match="options"):
            aq.validate_questions([{"text": "Pick", "type": "choice", "options": ["only one"]}])
        assert aq.validate_questions([{"text": "Audited?", "type": "yes_no", "good": "yes", "weight": 4}])[0]["weight"] == 4


class TestPortal:
    def test_a_supplier_answers_saves_a_draft_and_submits_once(self, client, apps, sarah):
        supplier = new_supplier(apps, org_of(sarah))
        sent, token = send(client, sarah, supplier)
        assert sent["assessment"]["status"] == "sent" and "Email is not configured" in sent["note"]
        seen = client.get("/api/v1/portal/assessment", headers=portal(token))
        assert seen.status_code == 200, seen.text
        view = seen.json()["assessment"]
        assert view["template_name"] == "Supply continuity" and view["supplier_name"].startswith("Orvane")
        assert "recipient_email" not in view and "token_hash" not in view
        assert client.put("/api/v1/portal/assessment", json={"answers": {"bcp": "yes"}},
                          headers=portal(token)).status_code == 200
        assert client.get("/api/v1/portal/assessment", headers=portal(token)).json()["assessment"]["answers"] == {"bcp": "yes"}
        incomplete = client.post("/api/v1/portal/assessment/submit", headers=portal(token),
                                 json={"answers": {"bcp": "yes"}, "name": "Dana", "email": "dana@supplier.example.com"})
        assert incomplete.status_code == 400
        done = client.post("/api/v1/portal/assessment/submit", headers=portal(token),
                           json={"answers": CONTINUITY_ANSWERS, "name": "Dana", "email": "dana@supplier.example.com"})
        assert done.status_code == 200, done.text
        # The link is spent: reading, saving and submitting again all get the same answer.
        for call in (lambda: client.get("/api/v1/portal/assessment", headers=portal(token)),
                     lambda: client.put("/api/v1/portal/assessment", json={"answers": {}}, headers=portal(token)),
                     lambda: client.post("/api/v1/portal/assessment/submit", headers=portal(token),
                                         json={"answers": CONTINUITY_ANSWERS, "name": "D", "email": "d@x.example.com"})):
            gone = call()
            assert gone.status_code == 404 and "not valid any more" in gone.json()["detail"]
        detail = client.get(f"/api/v1/assessments/{sent['assessment']['id']}", headers=bearer(sarah["access_token"])).json()
        assert detail["assessment"]["status"] == "submitted" and detail["assessment"]["score"] == round(100 * 8 / 13)
        assert detail["assessment"]["submitted_by_email"] == "dana@supplier.example.com"
        assert [link["name"] for link in detail["subtier"]] == ["Hexa API Ltd"]
        subtier = client.get(f"/api/v1/suppliers/{supplier}/subtier", headers=bearer(sarah["access_token"])).json()
        assert subtier["source"] == "supplier-reported" and subtier["links"][0]["country_code"] == "IN"

    def test_cancelled_resent_expired_and_unknown_links_get_one_answer(self, client, apps, sarah):
        supplier = new_supplier(apps, org_of(sarah))
        admin = bearer(sarah["access_token"])
        cancelled, cancelled_token = send(client, sarah, supplier)
        assert client.post(f"/api/v1/assessments/{cancelled['assessment']['id']}/cancel", headers=admin).status_code == 200
        resent, old_token = send(client, sarah, supplier)
        again = client.post(f"/api/v1/assessments/{resent['assessment']['id']}/resend", headers=admin)
        assert again.status_code == 200
        new_token = again.json()["portal_url"].split("#", 1)[1]
        expired, expired_token = send(client, sarah, supplier)
        store = apps["gateway"].audit_store
        asyncio.run(store.resend_assessment(org_of(sarah), expired["assessment"]["id"], portal_token_hash(expired_token),
                                            datetime.now(timezone.utc) - timedelta(minutes=1)))
        answers = set()
        for token in (cancelled_token, old_token, expired_token, "x" * 43, ""):
            response = client.get("/api/v1/portal/assessment", headers=portal(token))
            answers.add((response.status_code, response.json()["detail"]))
        assert len(answers) == 1 and answers.pop()[0] == 404
        assert client.get("/api/v1/portal/assessment", headers=portal(new_token)).status_code == 200

    def test_the_token_reaches_nothing_else_and_sessions_do_not_reach_the_portal(self, client, apps, sarah):
        supplier = new_supplier(apps, org_of(sarah))
        sent, token = send(client, sarah, supplier)
        for path in ("/api/v1/suppliers", f"/api/v1/assessments/{sent['assessment']['id']}", "/api/v1/audit"):
            assert client.get(path, headers=portal(token)).status_code in (401, 403), path
            assert client.get(path, headers=bearer(token)).status_code == 401, path
        # A signed-in session or an API key is not a portal token.
        assert client.get("/api/v1/portal/assessment", headers=bearer(sarah["access_token"])).status_code == 404
        key = client.post("/api/v1/org/api-keys", json={"name": "BI"}, headers=bearer(sarah["access_token"])).json()["key"]
        assert client.get("/api/v1/portal/assessment", headers=bearer(key)).status_code == 403

    def test_the_portal_ignores_a_session_sent_alongside_the_token(self, client, apps, sarah, lisa):
        """Another organization's session in the same browser changes nothing."""
        supplier = new_supplier(apps, org_of(sarah))
        _, token = send(client, sarah, supplier)
        seen = client.get("/api/v1/portal/assessment", headers={**portal(token), **bearer(lisa["access_token"])})
        assert seen.status_code == 200 and seen.json()["assessment"]["supplier_name"].startswith("Orvane")


class TestOrganizations:
    def test_assessments_and_links_stay_in_their_organization(self, client, apps, sarah, lisa):
        supplier = new_supplier(apps, org_of(sarah))
        sent, token = send(client, sarah, supplier)
        assert client.post("/api/v1/portal/assessment/submit", headers=portal(token),
                           json={"answers": CONTINUITY_ANSWERS, "name": "D", "email": "d@x.example.com"}).status_code == 200
        other = bearer(lisa["access_token"])
        assert client.get(f"/api/v1/assessments/{sent['assessment']['id']}", headers=other).status_code == 404
        assert sent["assessment"]["id"] not in [a["id"] for a in client.get("/api/v1/assessments", headers=other).json()["assessments"]]
        assert client.get(f"/api/v1/suppliers/{supplier}/subtier", headers=other).status_code == 404
        for action in ("cancel", "resend", "review"):
            assert client.post(f"/api/v1/assessments/{sent['assessment']['id']}/{action}", json={},
                               headers=other).status_code in (404, 409)

    def test_cannot_send_to_another_organizations_supplier(self, client, apps, sarah, lisa):
        theirs = new_supplier(apps, org_of(lisa))
        response = client.post("/api/v1/assessments", json={
            "supplier_id": theirs, "template_id": "builtin:quality", "recipient_email": "a@b.example.com"},
            headers=bearer(sarah["access_token"]))
        assert response.status_code == 404

    def test_custom_templates_are_private_to_the_organization(self, client, sarah, lisa):
        created = client.post("/api/v1/assessment-templates", json={
            "name": "Cold chain", "questions": [{"text": "Validated shipping lanes?", "type": "yes_no", "good": "yes"}]},
            headers=bearer(sarah["access_token"]))
        assert created.status_code == 200, created.text
        template_id = created.json()["template"]["id"]
        theirs = [t["id"] for t in client.get("/api/v1/assessment-templates", headers=bearer(lisa["access_token"])).json()["templates"]]
        assert template_id not in theirs and "builtin:continuity" in theirs
        assert client.delete(f"/api/v1/assessment-templates/{template_id}", headers=bearer(lisa["access_token"])).status_code == 404


class TestRolesAndReview:
    def test_read_only_roles_can_read_but_not_send_or_review(self, client, apps):
        team = make_org(apps, client)
        supplier = new_supplier(apps, org_of(team["admin"]))
        sent, _ = send(client, team["admin"], supplier)
        read_only = bearer(team["viewer"]["access_token"])
        assert client.get(f"/api/v1/assessments/{sent['assessment']['id']}", headers=read_only).status_code == 200
        assert client.post("/api/v1/assessments", json={"supplier_id": supplier, "template_id": "builtin:quality",
                                                         "recipient_email": "a@b.example.com"},
                           headers=read_only).status_code == 403
        assert client.post(f"/api/v1/assessments/{sent['assessment']['id']}/cancel", headers=read_only).status_code == 403

    def test_review_needs_a_submission_and_everything_is_audited(self, client, apps, sarah):
        supplier = new_supplier(apps, org_of(sarah))
        admin = bearer(sarah["access_token"])
        sent, token = send(client, sarah, supplier, template="builtin:quality")
        assessment = sent["assessment"]["id"]
        assert client.post(f"/api/v1/assessments/{assessment}/review", json={"note": "early"}, headers=admin).status_code == 409
        answers = {"gmp": "yes", "inspection_outcome": "No observations", "recall": "no", "change_notice": "yes"}
        assert client.post("/api/v1/portal/assessment/submit", headers=portal(token),
                           json={"answers": answers, "name": "Q", "email": "q@supplier.example.com"}).status_code == 200
        reviewed = client.post(f"/api/v1/assessments/{assessment}/review", json={"note": "Fine"}, headers=admin)
        assert reviewed.status_code == 200 and reviewed.json()["assessment"]["status"] == "reviewed"
        assert reviewed.json()["assessment"]["score"] == 100
        log = client.get("/api/v1/audit", params={"limit": 100}, headers=admin).json()["entries"]
        mine = {e["action"]: e for e in log if e.get("resource_id") == assessment and e["action"].startswith("assessment.")}
        assert set(mine) == {"assessment.sent", "assessment.submitted", "assessment.reviewed"}
        assert mine["assessment.submitted"]["actor"] == "supplier:q@supplier.example.com"
        assert not [e for e in log if "/api/v1/portal/" in e["action"]]  # drafts and reads are not logged
