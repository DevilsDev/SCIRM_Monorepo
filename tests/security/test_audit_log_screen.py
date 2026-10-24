"""
Audit log screen: filters, keyset paging and CSV export over the append-only audit log.
Runs on both backends, like the rest of the security suite.
"""

import asyncio
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from libs.common.store import audit_category

ORG1 = "a0000000-0000-0000-0000-000000000001"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def activity(client, login, sarah):
    """A failed and a good sign-in, an invitation, and an entry crafted to test CSV escaping."""
    login("sarah.chen@pharmacorp.com", "not-the-password")
    for _ in range(4):  # enough entries to page through
        login("sarah.chen@pharmacorp.com")
    client.post("/api/v1/org/invitations", json={"email": f"audit-{uuid.uuid4().hex[:6]}@example.com",
                                                 "roles": ["viewer"]}, headers=bearer(sarah["access_token"]))
    return True


def get(client, token, **params):
    response = client.get("/api/v1/audit", params=params, headers=bearer(token))
    assert response.status_code == 200, response.text
    return response.json()


def test_categories():
    assert audit_category("auth.login_failed") == "sign_in"
    assert audit_category("mfa.reset_by_admin") == "access"
    assert audit_category("POST /api/v1/org/invitations") == "access"
    assert audit_category("suppliers.import.sap") == "integrations"
    assert audit_category("PUT /api/v1/integrations/sap") == "integrations"
    assert audit_category("POST /api/v1/suppliers") == "changes"
    # Webhooks and reports, named or by route, are integrations (send-now was under access).
    for action in ("report.scheduled", "POST /api/v1/org/reports/{schedule_id}/send-now", "webhook.created",
                   "PATCH /api/v1/org/webhooks/{webhook_id}"):
        assert audit_category(action) == "integrations", action
    for action in ("sso.enforcement_off", "scim.user_deactivated", "PATCH /scim/v2/Users/{user_id}",
                   "PUT /api/v1/org/sso", "DELETE /api/v1/org/api-keys/{key_id}"):
        assert audit_category(action) == "access", action


def test_categories_do_not_overlap():
    """PostgreSQL filters each category by its own patterns, so an action matching two
    categories would be listed under both."""
    from libs.common.store import AUDIT_CATEGORIES, _like
    actions = ["auth.login", "mfa.enabled", "sso.updated", "scim.user_created", "api_key.refused", "report.deleted",
               "webhook.created", "integrations.sap.save", "suppliers.import.sap"]
    actions += [f"POST /api/v1/org/{r}" for r in ("invitations", "members/{member_id}/mfa/reset", "api-keys",
                                                  "webhooks", "reports/{schedule_id}/send-now")]
    actions += ["PUT /api/v1/org/sso", "POST /scim/v2/Users", "POST /api/v1/auth/forgot-password"]
    for action in actions:
        hits = [name for name, patterns in AUDIT_CATEGORIES.items() if any(_like(p, action) for p in patterns)]
        assert len(hits) == 1, (action, hits)


class TestFilters:
    def test_each_category_returns_only_its_entries(self, client, sarah, activity):
        for category in ("sign_in", "access", "integrations", "changes"):
            entries = get(client, sarah["access_token"], category=category, limit=200)["entries"]
            assert all(e["category"] == category for e in entries), category
        assert any(e["action"] == "auth.login_failed" for e in get(client, sarah["access_token"], category="sign_in")["entries"])
        assert any(e["action"] == "POST /api/v1/org/invitations"
                   for e in get(client, sarah["access_token"], category="access")["entries"])

    def test_failed_and_actor(self, client, sarah, activity):
        failed = get(client, sarah["access_token"], failed="true", limit=200)["entries"]
        assert failed and all(e["status_code"] >= 400 for e in failed)
        # A wrong password on an existing account shows in its organization's log, with the address.
        wrong = [e for e in failed if e["action"] == "auth.login_failed" and e["actor"] == "sarah.chen@pharmacorp.com"]
        assert wrong and wrong[0]["ip_address"]
        mine = get(client, sarah["access_token"], actor="SARAH.CHEN", limit=200)["entries"]
        assert mine and all("sarah.chen" in e["actor"] for e in mine)

    def test_time_range(self, client, sarah, activity):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        assert get(client, sarah["access_token"], since=future)["entries"] == []
        assert get(client, sarah["access_token"], until="2000-01-01")["entries"] == []

    def test_bad_input_is_refused(self, client, sarah):
        for params in ({"category": "everything"}, {"since": "yesterday"}, {"before": "nope"}):
            assert client.get("/api/v1/audit", params=params, headers=bearer(sarah["access_token"])).status_code == 400


class TestPaging:
    def test_pages_follow_on_without_gaps_or_repeats(self, client, sarah, activity):
        everything = get(client, sarah["access_token"], limit=500)["entries"]
        assert len(everything) >= 5
        seen, cursor = [], None
        while len(seen) < 5:
            page = get(client, sarah["access_token"], limit=2, **({"before": cursor} if cursor else {}))
            seen.extend(e["id"] for e in page["entries"])
            cursor = page["next_cursor"]
            assert cursor
        assert seen == [e["id"] for e in everything[:len(seen)]]

    def test_the_last_page_has_no_cursor(self, client, sarah, activity):
        page = get(client, sarah["access_token"], limit=500)
        assert page["next_cursor"] is None or len(page["entries"]) == 500


class TestExport:
    def test_csv_with_escaped_formulas_and_its_own_audit_entry(self, client, apps, sarah, activity):
        asyncio.run(apps["gateway"].audit_store.record_audit(ORG1, {
            "actor_type": "user", "actor": "=HYPERLINK(\"http://x\")", "action": "auth.login_failed",
            "resource_type": "auth", "status_code": 401}))
        response = client.get("/api/v1/audit/export", params={"category": "sign_in"},
                              headers=bearer(sarah["access_token"]))
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert rows and all(r["category"] == "sign_in" for r in rows)
        crafted = [r for r in rows if "HYPERLINK" in r["actor"]]
        assert crafted and all(r["actor"].startswith("'=") for r in crafted)
        assert any(e["action"] == "audit.exported" for e in get(client, sarah["access_token"], category="changes")["entries"])

    def test_only_admins_and_auditors(self, client, login):
        analyst = login("marcus.rodriguez@pharmacorp.com").json().get("access_token")
        if analyst:  # Marcus may have MFA on from another test; then he cannot get a token here
            assert client.get("/api/v1/audit/export", headers=bearer(analyst)).status_code == 403


def test_other_tenants_entries_never_appear(client, lisa, activity):
    entries = get(client, lisa["access_token"], limit=500)["entries"]
    assert all("pharmacorp" not in (e.get("actor") or "") for e in entries)
