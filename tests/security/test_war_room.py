"""
War room: incidents opened from a public record (suppliers prefilled from its matches) or
by hand, with an owner, tasks for members, linked suppliers, spend exposure per currency
and an append-only timeline. Tenant data; read-only roles can read. Runs on both backends.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def org_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["org_id"]


def email_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["email"]


def supplier(apps, org, name, **extra) -> str:
    created = asyncio.run(apps["gateway"].audit_store.create_supplier(org, {
        "name": name, "supplier_code": f"WR-{uuid.uuid4().hex[:6]}", "supplier_type": "manufacturer",
        "country_code": "IN", **extra}))
    return str(created["id"])


def recall_naming(apps, firm: str) -> str:
    store = apps["gateway"].audit_store
    tag = uuid.uuid4().hex[:6]
    record = {"source": "fda_recalls", "external_id": f"WR-{tag}", "signal_type": "recall",
              "title": f"Class I recall: {firm} sterile injectables", "summary": "Lack of sterility assurance.",
              "severity": "critical", "entity_names": [firm], "entity_keys": [], "country_codes": [],
              "published_at": datetime.now(timezone.utc).date().isoformat(), "updated_at": None,
              "url": "https://example.test/recall", "raw": {"classification": "Class I", "recalling_firm": firm,
                                                            "event_id": f"E-{tag}"}}
    from libs.intel.matching import entity_keys
    record["entity_keys"] = entity_keys([firm])
    asyncio.run(store.upsert_signals([record]))
    found = asyncio.run(store.list_signals(source="fda_recalls", limit=500))[0]
    return next(str(s["id"]) for s in found if s["external_id"] == record["external_id"])


class TestOpening:
    def test_from_a_record_prefills_title_severity_and_the_named_supplier(self, client, apps, new_team):
        team = new_team(("admin",))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        firm = f"Hexavane Sterile {uuid.uuid4().hex[:4]}"
        named = supplier(apps, org, firm, spend_12m={"EUR": "1000.50", "USD": "20"})
        supplier(apps, org, "Unrelated Packaging Ltd")
        signal_id = recall_naming(apps, firm)
        opened = client.post("/api/v1/incidents", json={"signal_id": signal_id}, headers=admin)
        assert opened.status_code == 200, opened.text
        body = opened.json()
        incident = body["incident"]
        assert incident["title"].startswith("Class I recall:") and incident["severity"] == "critical"
        assert incident["status"] == "open" and incident["signal"]["source_label"] == "FDA drug recalls"
        assert [s["id"] for s in body["suppliers"]] == [named]
        assert body["exposure"] == {"by_currency": {"EUR": "1000.50", "USD": "20"}, "without_spend": 0}
        assert [e["kind"] for e in body["timeline"]] == ["opened", "supplier_added"]

    def test_by_hand_needs_a_title_and_own_suppliers(self, client, apps, new_team):
        team, other = new_team(("admin",)), new_team(("admin",))
        admin = bearer(team["admin"]["access_token"])
        assert client.post("/api/v1/incidents", json={}, headers=admin).status_code == 400
        theirs = supplier(apps, org_of(other["admin"]), "Their Supplier")
        assert client.post("/api/v1/incidents", json={"title": "x", "supplier_ids": [theirs]}, headers=admin).status_code == 404
        assert client.post("/api/v1/incidents", json={"signal_id": str(uuid.uuid4())}, headers=admin).status_code == 404


class TestWorking:
    def test_owner_tasks_suppliers_notes_and_status_are_on_the_timeline(self, client, apps, new_team):
        team = new_team(("admin", "analyst", "viewer"))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        analyst = email_of(team["analyst"])
        a = supplier(apps, org, "Alpha API GmbH", spend_12m={"EUR": "100"})
        b = supplier(apps, org, "Beta Excipients", spend_12m={"EUR": "50.25", "JPY": "7000"})
        c = supplier(apps, org, "Gamma Labels")
        iid = client.post("/api/v1/incidents", json={"title": "Port strike", "supplier_ids": [a]}, headers=admin).json()["incident"]["id"]
        path = f"/api/v1/incidents/{iid}"
        assert client.patch(path, json={"owner_email": "stranger@elsewhere.example.com"}, headers=admin).status_code == 400
        assert client.patch(path, json={"owner_email": analyst, "status": "monitoring", "severity": "high"},
                            headers=admin).status_code == 200
        for sid in (b, c):
            assert client.post(f"{path}/suppliers", json={"supplier_id": sid, "reason": "ships via the port"},
                               headers=admin).status_code == 200
        assert client.post(f"{path}/suppliers", json={"supplier_id": b}, headers=admin).status_code == 409
        assert client.delete(f"{path}/suppliers/{c}", headers=admin).status_code == 200
        task = client.post(f"{path}/tasks", json={"title": "Call Beta about stock", "assignee_email": analyst,
                                                   "due_date": "2026-11-01"}, headers=admin).json()["tasks"][0]
        assert client.post(f"{path}/tasks", json={"title": "x", "assignee_email": "nobody@x.example.com"},
                           headers=admin).status_code == 400
        assert client.patch(f"{path}/tasks/{task['id']}", json={"status": "done"}, headers=admin).json()["tasks"][0]["status"] == "done"
        client.post(f"{path}/notes", json={"text": "Beta confirms 6 weeks of stock."}, headers=admin)
        done = client.patch(path, json={"status": "resolved", "resolution": "Strike ended"}, headers=admin).json()
        assert done["incident"]["status"] == "resolved" and done["incident"]["resolved_at"]
        assert done["exposure"] == {"by_currency": {"EUR": "150.25", "JPY": "7000"}, "without_spend": 0}
        kinds = [e["kind"] for e in done["timeline"]]
        assert kinds.count("supplier_added") == 3 and "supplier_removed" in kinds and "task_done" in kinds
        assert {"owner", "status", "severity", "note"} <= set(kinds)
        assert done["timeline"][-1]["text"] == "Status: monitoring → resolved. Resolution: Strike ended"
        listed = client.get("/api/v1/incidents", headers=bearer(team["viewer"]["access_token"])).json()
        assert listed["incidents"][0]["supplier_count"] == 2 and listed["incidents"][0]["open_tasks"] == 0
        assert analyst in listed["members"]

    def test_read_only_roles_can_read_but_not_change(self, client, new_team):
        team = new_team(("admin", "viewer"))
        viewer = bearer(team["viewer"]["access_token"])
        iid = client.post("/api/v1/incidents", json={"title": "Flood"}, headers=bearer(team["admin"]["access_token"])).json()["incident"]["id"]
        assert client.get(f"/api/v1/incidents/{iid}", headers=viewer).status_code == 200
        assert client.post("/api/v1/incidents", json={"title": "x"}, headers=viewer).status_code == 403
        for call in (lambda: client.patch(f"/api/v1/incidents/{iid}", json={"status": "resolved"}, headers=viewer),
                     lambda: client.post(f"/api/v1/incidents/{iid}/notes", json={"text": "x"}, headers=viewer),
                     lambda: client.post(f"/api/v1/incidents/{iid}/tasks", json={"title": "x"}, headers=viewer)):
            assert call().status_code == 403

    def test_incidents_stay_in_their_organization(self, client, apps, new_team):
        ours, theirs = new_team(("admin",)), new_team(("admin",))
        other = bearer(theirs["admin"]["access_token"])
        iid = client.post("/api/v1/incidents", json={"title": "Ours"}, headers=bearer(ours["admin"]["access_token"])).json()["incident"]["id"]
        assert client.get(f"/api/v1/incidents/{iid}", headers=other).status_code == 404
        assert client.get("/api/v1/incidents", headers=other).json()["incidents"] == []
        assert client.patch(f"/api/v1/incidents/{iid}", json={"status": "resolved"}, headers=other).status_code == 404
        assert client.post(f"/api/v1/incidents/{iid}/notes", json={"text": "x"}, headers=other).status_code == 404
        mine = supplier(apps, org_of(theirs["admin"]), "Their Own Supplier")
        assert client.post(f"/api/v1/incidents/{iid}/suppliers", json={"supplier_id": mine}, headers=other).status_code == 404
        assert client.post(f"/api/v1/incidents/{iid}/tasks", json={"title": "x"}, headers=other).status_code == 404

    def test_opening_and_status_changes_are_audited(self, client, new_team):
        team = new_team(("admin",))
        admin = bearer(team["admin"]["access_token"])
        iid = client.post("/api/v1/incidents", json={"title": "Audit me"}, headers=admin).json()["incident"]["id"]
        client.patch(f"/api/v1/incidents/{iid}", json={"status": "monitoring"}, headers=admin)
        log = client.get("/api/v1/audit", params={"limit": 50}, headers=admin).json()["entries"]
        named = {e["action"]: e for e in log if e.get("resource_id") == iid and e["action"].startswith("incident.")}
        assert set(named) == {"incident.opened", "incident.status_changed"}
        assert named["incident.status_changed"]["details"] == {"from": "open", "to": "monitoring"}
