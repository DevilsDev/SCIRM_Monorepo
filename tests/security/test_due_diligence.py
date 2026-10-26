"""
Human rights and environmental due diligence (LkSG, CSDDD): a risk register per supplier
rated by people with a reason, measures with owners and an effectiveness review, the
periodic review of the risk analysis, the yearly documentation, and the due-diligence
questionnaire (flags, never a score; sent only with a reason). Runs on both backends.
"""

import asyncio
import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.assessments import questions as aq
from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token
from libs.due_diligence import catalog as dd

ROOT = Path(__file__).resolve().parents[2]


def bearer(tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def org_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["org_id"]


def email_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["email"]


def supplier(apps, org, name="Diligent Textiles") -> str:
    created = asyncio.run(apps["gateway"].audit_store.create_supplier(org, {
        "name": name, "supplier_code": f"DD-{uuid.uuid4().hex[:6]}", "supplier_type": "manufacturer"}))
    return str(created["id"])


def risk(client, headers, sid, area="occupational_safety", likelihood=3, severity=2, **extra):
    return client.post("/api/v1/due-diligence/risks", headers=headers, json={
        "supplier_id": sid, "area": area, "description": "Excessive overtime on the night shift",
        "likelihood": likelihood, "severity": severity, "rating_reason": "Audit report, March", "source": "in_depth",
        **extra})


def test_the_catalogue_follows_the_law_and_the_migration():
    spec = importlib.util.spec_from_file_location("m032", ROOT / "alembic" / "versions" / "032_due_diligence.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert set(migration.AREAS) == set(dd.AREAS) and set(migration.SOURCES) == set(dd.SOURCES)
    assert set(migration.KINDS) == set(dd.MEASURE_KINDS)
    lksg = {a["lksg"] for a in dd.AREAS.values()}
    assert all(f"§ 2(2) no. {n}" in lksg for n in range(1, 13)), "every human-rights prohibition of LkSG § 2(2)"
    assert all(f"§ 2(3) no. {n}" in lksg for n in range(1, 9)), "every environmental prohibition of LkSG § 2(3)"
    assert set(dd.LAST_RESORT) <= set(dd.MEASURE_KINDS)


def test_the_due_diligence_questionnaire_raises_flags_and_never_a_score():
    template = aq.BUILT_IN["builtin:due_diligence"]
    questions = template["questions"]
    assert template["due_diligence"] and all(q.get("help") for q in questions if q.get("flag_only"))
    answers = {q["id"]: q["good"] for q in questions if q.get("good")}
    assert aq.score(questions, answers) == (None, [])
    answers["forced_labour"] = "yes"
    score, flags = aq.score(questions, answers)
    assert score is None and [f["id"] for f in flags] == ["forced_labour"]
    # Other questionnaires still score.
    assert aq.score(aq.BUILT_IN["builtin:quality"]["questions"], {"gmp": "yes"})[0] == 100


def test_asking_a_supplier_for_due_diligence_information_needs_a_reason(apps, client, new_team):
    team = new_team(("admin",))
    admin = bearer(team["admin"])
    sid = supplier(apps, org_of(team["admin"]))
    body = {"supplier_id": sid, "template_id": "builtin:due_diligence", "recipient_email": "ops@supplier.example.com",
            "send_email": False}
    refused = client.post("/api/v1/assessments", headers=admin, json=body)
    assert refused.status_code == 400 and "8(2a)" in refused.json()["detail"]
    sent = client.post("/api/v1/assessments", headers=admin, json={
        **body, "request_reason": "Night-shift overtime found in the March audit; their own records are needed."})
    assert sent.status_code == 200, sent.text
    assert sent.json()["assessment"]["request_reason"].startswith("Night-shift")
    listed = client.get("/api/v1/assessments", params={"supplier_id": sid}, headers=admin).json()["assessments"]
    assert listed[0]["request_reason"].startswith("Night-shift")
    # Other questionnaires need no reason.
    other = client.post("/api/v1/assessments", headers=admin, json={**body, "template_id": "builtin:quality"})
    assert other.status_code == 200 and other.json()["assessment"]["request_reason"] is None


class TestRiskRegister:
    def test_people_rate_risks_with_a_reason_and_the_register_is_prioritised(self, apps, client, new_team):
        team = new_team(("admin", "viewer"))
        admin, viewer = bearer(team["admin"]), bearer(team["viewer"])
        sid = supplier(apps, org_of(team["admin"]))
        assert risk(client, viewer, sid).status_code == 403
        assert risk(client, admin, sid, rating_reason="").status_code == 422
        assert risk(client, admin, sid, area="made_up").status_code == 400
        assert risk(client, admin, sid, likelihood=5).status_code == 422
        low = risk(client, admin, sid, "fair_wage", likelihood=4, severity=1).json()["risk"]
        high = risk(client, admin, sid, "forced_labour", likelihood=1, severity=4).json()["risk"]
        mid = risk(client, admin, sid, "occupational_safety", likelihood=3, severity=4).json()["risk"]
        view = client.get(f"/api/v1/due-diligence/suppliers/{sid}", headers=viewer).json()
        assert [r["id"] for r in view["risks"]] == [mid["id"], high["id"], low["id"]]  # severity, then likelihood
        assert mid["assessed_by"] == email_of(team["admin"])
        # A new rating needs its reason; the history keeps the old and the new.
        patch = f"/api/v1/due-diligence/risks/{low['id']}"
        assert client.patch(patch, headers=admin, json={"severity": 3}).status_code == 400
        rerated = client.patch(patch, headers=admin, json={"severity": 3, "rating_reason": "Wage slips withheld"})
        assert rerated.status_code == 200 and rerated.json()["risk"]["severity"] == 3
        assert client.patch(patch, headers=admin, json={"status": "made_up"}).status_code == 400
        assert client.patch(patch, headers=admin, json={"status": "mitigated"}).status_code == 200
        history = client.get(f"/api/v1/due-diligence/suppliers/{sid}", headers=admin).json()["history"]
        assert [e["kind"] for e in history] == ["risk_added"] * 3 + ["risk_rated", "risk_status"]
        assert "Wage slips withheld" in history[3]["text"] and "mitigated" in history[4]["text"]
        log = client.get("/api/v1/audit", params={"limit": 50}, headers=admin).json()["entries"]
        assert sum(1 for e in log if e["action"] == "due_diligence.risk_added") == 3

    def test_measures_have_members_as_owners_and_their_effectiveness_is_reviewed(self, apps, client, new_team):
        team = new_team(("admin",))
        admin = bearer(team["admin"])
        org = org_of(team["admin"])
        sid, other = supplier(apps, org), supplier(apps, org, "Other Ltd")
        rid = risk(client, admin, sid).json()["risk"]["id"]
        url = "/api/v1/due-diligence/measures"
        body = {"supplier_id": sid, "risk_id": rid, "kind": "corrective_action_plan", "description": "Shift plan"}
        assert client.post(url, headers=admin, json={**body, "owner_email": "stranger@example.com"}).status_code == 400
        assert client.post(url, headers=admin, json={**body, "supplier_id": other}).status_code == 404
        assert client.post(url, headers=admin, json={**body, "kind": "made_up"}).status_code == 400
        measure = client.post(url, headers=admin, json={**body, "owner_email": email_of(team["admin"]),
                                                        "due_date": "2026-12-31"})
        assert measure.status_code == 200, measure.text
        mid = measure.json()["measure"]["id"]
        done = client.patch(f"{url}/{mid}", headers=admin, json={"status": "done"})
        assert done.json()["measure"]["status"] == "done"
        reviewed = client.patch(f"{url}/{mid}", headers=admin, json={
            "effectiveness": "partly_effective", "effectiveness_note": "Overtime down, not yet within the limit"})
        assert reviewed.json()["measure"]["effectiveness"] == "partly_effective"
        assert client.patch(f"{url}/{mid}", headers=admin, json={"status": None}).status_code == 400
        last_resort = client.post(url, headers=admin, json={**body, "kind": "suspend", "description": "Pause new orders"})
        assert last_resort.status_code == 200
        kinds = [e["kind"] for e in client.get(f"/api/v1/due-diligence/suppliers/{sid}", headers=admin).json()["history"]]
        assert kinds == ["risk_added", "measure_added", "measure_status", "measure_reviewed", "measure_added"]
        log = client.get("/api/v1/audit", params={"limit": 50}, headers=admin).json()["entries"]
        assert any(e["action"] == "due_diligence.measure_added" and e["details"].get("last_resort") for e in log)

    def test_another_organization_sees_and_touches_nothing(self, apps, client, new_team):
        team, stranger_team = new_team(("admin",)), new_team(("admin",))
        admin, stranger = bearer(team["admin"]), bearer(stranger_team["admin"])
        sid = supplier(apps, org_of(team["admin"]))
        rid = risk(client, admin, sid).json()["risk"]["id"]
        assert client.get(f"/api/v1/due-diligence/suppliers/{sid}", headers=stranger).status_code == 404
        assert risk(client, stranger, sid).status_code == 404
        assert client.patch(f"/api/v1/due-diligence/risks/{rid}", headers=stranger,
                            json={"status": "closed"}).status_code == 404
        assert client.post("/api/v1/due-diligence/reviews", headers=stranger,
                           json={"supplier_id": sid, "conclusion": "x"}).status_code == 404
        assert client.get("/api/v1/due-diligence/overview", headers=stranger).json()["suppliers"] == []


class TestReviewCycle:
    def test_review_states(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        assert dd.review_status(None, 12, [], now)["state"] == "not_analysed"
        last = now - timedelta(days=30)
        assert dd.review_status(last, 12, [], now)["state"] == "current"
        assert dd.review_status(last, 12, [], now)["next_review"].startswith("2027-09-25")
        change = {"at": now - timedelta(days=2), "text": "War-room incident: Fire"}
        suggested = dd.review_status(last, 12, [change], now)
        assert suggested["state"] == "suggested" and suggested["reasons"] == ["War-room incident: Fire"]
        assert dd.review_status(now - timedelta(days=400), 12, [], now)["state"] == "due"
        assert dd.review_status(datetime(2026, 1, 31, tzinfo=timezone.utc), 1, [], now)["next_review"].startswith(
            "2026-02-28")

    def test_a_review_is_recorded_and_a_later_incident_suggests_another(self, apps, client, new_team):
        team = new_team(("admin", "viewer"))
        admin, viewer = bearer(team["admin"]), bearer(team["viewer"])
        sid = supplier(apps, org_of(team["admin"]))
        overview = {s["supplier_id"]: s for s in client.get("/api/v1/due-diligence/overview", headers=viewer).json()["suppliers"]}
        assert overview[sid]["review"]["state"] == "not_analysed" and overview[sid]["top_risk"] is None
        reviewed = client.post("/api/v1/due-diligence/reviews", headers=admin,
                               json={"supplier_id": sid, "conclusion": "No priority risks beyond overtime."})
        assert reviewed.status_code == 200 and reviewed.json()["state"]["state"] == "current"
        incident = client.post("/api/v1/incidents", headers=admin, json={"title": "Factory fire"}).json()["incident"]["id"]
        client.post(f"/api/v1/incidents/{incident}/suppliers", headers=admin, json={"supplier_id": sid})
        state = client.get(f"/api/v1/due-diligence/suppliers/{sid}", headers=viewer).json()["review"]
        assert state["state"] == "suggested" and state["reasons"] == ["War-room incident: Factory fire"]

    def test_only_administrators_set_the_interval(self, client, new_team):
        team = new_team(("admin", "analyst"))
        admin, analyst = bearer(team["admin"]), bearer(team["analyst"])
        assert client.get("/api/v1/due-diligence/settings", headers=analyst).json() == {"review_months": 12}
        assert client.put("/api/v1/due-diligence/settings", headers=analyst, json={"review_months": 6}).status_code == 403
        assert client.put("/api/v1/due-diligence/settings", headers=admin, json={"review_months": 61}).status_code == 422
        assert client.put("/api/v1/due-diligence/settings", headers=admin, json={"review_months": 6}).json() == {"review_months": 6}
        assert client.get("/api/v1/due-diligence/settings", headers=analyst).json() == {"review_months": 6}


def test_the_yearly_documentation(apps, client, new_team):
    team = new_team(("admin",))
    admin = bearer(team["admin"])
    sid = supplier(apps, org_of(team["admin"]), "=HYPERLINK Ltd")
    rid = risk(client, admin, sid).json()["risk"]["id"]
    mid = client.post("/api/v1/due-diligence/measures", headers=admin, json={
        "supplier_id": sid, "risk_id": rid, "kind": "audit", "description": "Follow-up audit"}).json()["measure"]["id"]
    client.patch(f"/api/v1/due-diligence/measures/{mid}", headers=admin, json={"effectiveness": "effective"})
    client.post("/api/v1/due-diligence/reviews", headers=admin, json={"supplier_id": sid, "conclusion": "Keep auditing."})
    year = datetime.now(timezone.utc).year
    doc = client.get("/api/v1/due-diligence/export", params={"year": year}, headers=admin)
    assert doc.status_code == 200 and "attachment" in doc.headers["content-disposition"]
    body = doc.json()
    assert [r["id"] for r in body["risks_identified"]] == [rid] and body["risks_identified"][0]["lksg"] == "§ 2(2) no. 5"
    assert [m["id"] for m in body["measures"]] == [mid]
    assert len(body["effectiveness"]) == 1 and body["conclusions"][0]["text"] == "Keep auditing."
    assert client.get("/api/v1/due-diligence/export", params={"year": year - 1}, headers=admin).json()["history"] == []
    csv = client.get("/api/v1/due-diligence/export", params={"year": year, "format": "csv"}, headers=admin)
    assert csv.headers["content-type"].startswith("text/csv") and "'=HYPERLINK Ltd" in csv.text
    assert client.get("/api/v1/due-diligence/export", params={"year": year, "format": "xml"}, headers=admin).status_code == 400
    log = client.get("/api/v1/audit", params={"limit": 20}, headers=admin).json()["entries"]
    assert any(e["action"] == "due_diligence.exported" for e in log)
