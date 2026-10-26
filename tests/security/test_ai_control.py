"""
AI control centre: the action policy (never / approval / allowed, with actions that leave
the organization capped at approval), the approval queue (an approved action runs through
the same function and checks as when a person does it; decided once), and the AI run log
(every Ask, readable by admins and auditors). Runs on both backends.
"""

import asyncio
import uuid

import pytest

from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token
from libs.common.models import User


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def org_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["org_id"]


def agent(org: str) -> User:
    """How an MCP key appears to the gateway: an analyst-level identity named after the key."""
    return User(id=str(uuid.uuid4()), email="api-key:Claude Desktop (scirm_testkey)", name="Claude Desktop",
                roles=["analyst"], organization_id=org)


def propose(apps, who, action, params, summary="Proposed by a test agent"):
    return asyncio.run(apps["gateway"].propose_action(who, action, params, summary))


class TestPolicy:
    def test_defaults_and_only_admins_change_it(self, client, new_team):
        team = new_team(("admin", "analyst"))
        admin, analyst = bearer(team["admin"]["access_token"]), bearer(team["analyst"]["access_token"])
        policy = {a["action"]: a for a in client.get("/api/v1/ai/policy", headers=analyst).json()["actions"]}
        assert policy["assessment.send"]["mode"] == "never" and policy["assessment.send"]["external"] is True
        assert policy["incident.open"]["mode"] == "approval"
        assert client.put("/api/v1/ai/policy", json={"action": "incident.open", "mode": "allowed"},
                          headers=analyst).status_code == 403
        changed = client.put("/api/v1/ai/policy", json={"action": "incident.open", "mode": "allowed"}, headers=admin)
        assert changed.status_code == 200
        assert {a["action"]: a["mode"] for a in changed.json()["actions"]}["incident.open"] == "allowed"
        log = client.get("/api/v1/audit", params={"category": "access", "limit": 50}, headers=admin).json()["entries"]
        entry = next(e for e in log if e["action"] == "action.policy_changed")
        assert entry["details"] == {"action": "incident.open", "from": "approval", "to": "allowed"}

    def test_actions_that_leave_the_organization_always_need_a_person(self, client, new_team):
        admin = bearer(new_team(("admin",))["admin"]["access_token"])
        refused = client.put("/api/v1/ai/policy", json={"action": "assessment.send", "mode": "allowed"}, headers=admin)
        assert refused.status_code == 400 and "outside the organization" in refused.json()["detail"]
        assert client.put("/api/v1/ai/policy", json={"action": "made.up", "mode": "never"}, headers=admin).status_code == 400


class TestProposals:
    def test_queued_then_approved_once_through_the_normal_checks(self, client, apps, new_team):
        team = new_team(("admin", "viewer"))
        org, admin, viewer = org_of(team["admin"]), bearer(team["admin"]["access_token"]), bearer(team["viewer"]["access_token"])
        proposal = propose(apps, agent(org), "incident.open", {"title": "Port strike in Rotterdam"},
                           "Strike reported by three news sources")
        assert proposal["status"] == "pending" and proposal["proposed_by"].startswith("api-key:Claude Desktop")
        listed = client.get("/api/v1/ai/proposals", params={"status": "pending"}, headers=viewer).json()["proposals"]
        assert [p["id"] for p in listed] == [proposal["id"]] and listed[0]["label"] == "Open a war-room incident"
        assert client.post(f"/api/v1/ai/proposals/{proposal['id']}/approve", json={}, headers=viewer).status_code == 403
        approved = client.post(f"/api/v1/ai/proposals/{proposal['id']}/approve", json={"note": "Confirmed"}, headers=admin)
        assert approved.status_code == 200, approved.text
        done = approved.json()["proposal"]
        assert done["status"] == "executed" and done["decided_by"] == decode_token(team["admin"]["access_token"], TOKEN_TYPE_ACCESS)["email"]
        incident = client.get(f"/api/v1/incidents/{done['result']['incident_id']}", headers=viewer).json()["incident"]
        assert incident["title"] == "Port strike in Rotterdam"
        assert client.post(f"/api/v1/ai/proposals/{proposal['id']}/approve", json={}, headers=admin).status_code == 409
        assert client.post(f"/api/v1/ai/proposals/{proposal['id']}/reject", json={}, headers=admin).status_code == 409
        log = client.get("/api/v1/audit", params={"limit": 100}, headers=admin).json()["entries"]
        mine = {e["action"]: e for e in log if e.get("resource_id") == proposal["id"]}
        assert mine["action.proposed"]["actor"].startswith("api-key:") and "action.executed" in mine

    def test_never_refuses_and_allowed_runs_directly(self, client, apps, new_team):
        team = new_team(("admin",))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        with pytest.raises(apps["gateway"].ActionRefused):
            propose(apps, agent(org), "assessment.send", {"supplier_id": str(uuid.uuid4()),
                                                          "template_id": "builtin:quality", "recipient_email": "a@b.example.com"})
        client.put("/api/v1/ai/policy", json={"action": "watchlist.add", "mode": "allowed"}, headers=admin)
        done = propose(apps, agent(org), "watchlist.add", {"term": "rifampicin"})
        assert done["status"] == "executed" and done["decided_by"].startswith("api-key:")
        assert [i["term"] for i in client.get("/api/v1/watchlist", headers=admin).json()["items"]] == ["rifampicin"]

    def test_bad_parameters_never_reach_the_queue_and_failures_are_recorded(self, client, apps, new_team):
        team = new_team(("admin",))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        with pytest.raises(ValueError):
            propose(apps, agent(org), "watchlist.add", {"term": "x"})  # too short for the request model
        assert client.get("/api/v1/ai/proposals", headers=admin).json()["proposals"] == []
        bad = propose(apps, agent(org), "incident.note", {"incident_id": str(uuid.uuid4()), "text": "hello"})
        failed = client.post(f"/api/v1/ai/proposals/{bad['id']}/approve", json={}, headers=admin).json()["proposal"]
        assert failed["status"] == "failed" and failed["result"] == {"error": "Incident not found"}
        rejected = propose(apps, agent(org), "incident.open", {"title": "Not real"})
        out = client.post(f"/api/v1/ai/proposals/{rejected['id']}/reject", json={"note": "Rumour"}, headers=admin).json()
        assert out["proposal"]["status"] == "rejected" and out["proposal"]["decision_note"] == "Rumour"

    def test_a_due_diligence_questionnaire_without_a_reason_never_reaches_the_queue(self, client, apps, new_team):
        team = new_team(("admin",))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        supplier = asyncio.run(apps["gateway"].audit_store.create_supplier(org, {
            "name": "Agent Diligence Ltd", "supplier_code": f"AD-{uuid.uuid4().hex[:6]}", "supplier_type": "manufacturer"}))
        client.put("/api/v1/ai/policy", json={"action": "assessment.send", "mode": "approval"}, headers=admin)
        params = {"supplier_id": str(supplier["id"]), "template_id": "builtin:due_diligence",
                  "recipient_email": "ehs@supplier.example.com"}
        with pytest.raises(ValueError, match=r"8\(2a\)"):
            propose(apps, agent(org), "assessment.send", params)
        assert client.get("/api/v1/ai/proposals", headers=admin).json()["proposals"] == []
        queued = propose(apps, agent(org), "assessment.send", {**params, "request_reason": "Audit found overtime"})
        assert queued["status"] == "pending"

    def test_a_supplier_link_goes_to_the_approver_once_and_is_not_stored(self, client, apps, new_team):
        team = new_team(("admin",))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        supplier = asyncio.run(apps["gateway"].audit_store.create_supplier(org, {
            "name": "Agent Proposed GmbH", "supplier_code": f"AP-{uuid.uuid4().hex[:6]}", "supplier_type": "manufacturer"}))
        client.put("/api/v1/ai/policy", json={"action": "assessment.send", "mode": "approval"}, headers=admin)
        proposal = propose(apps, agent(org), "assessment.send", {"supplier_id": str(supplier["id"]),
                                                                  "template_id": "builtin:quality",
                                                                  "recipient_email": "qa@supplier.example.com"})
        approved = client.post(f"/api/v1/ai/proposals/{proposal['id']}/approve", json={}, headers=admin).json()["proposal"]
        assert approved["status"] == "executed" and "/portal#" in approved["portal_url"]
        stored = client.get("/api/v1/ai/proposals", headers=admin).json()["proposals"][0]
        assert "portal_url" not in stored and "_portal_url" not in (stored["result"] or {})

    def test_proposals_stay_in_their_organization(self, client, apps, new_team):
        ours, theirs = new_team(("admin",)), new_team(("admin",))
        proposal = propose(apps, agent(org_of(ours["admin"])), "incident.open", {"title": "Ours"})
        other = bearer(theirs["admin"]["access_token"])
        assert client.get("/api/v1/ai/proposals", headers=other).json()["proposals"] == []
        assert client.post(f"/api/v1/ai/proposals/{proposal['id']}/approve", json={}, headers=other).status_code == 409


class TestRunLog:
    def test_every_ask_is_logged_for_admins_and_auditors(self, client, apps, new_team):
        team = new_team(("admin", "analyst", "auditor"))
        org = org_of(team["admin"])
        # Ask goes through the coordinator, which reads its own store (the same database on PostgreSQL).
        supplier = asyncio.run(apps["coordinator"].store.create_supplier(org, {
            "name": f"Quietly Fine Chemicals {uuid.uuid4().hex[:4]}", "supplier_code": f"RL-{uuid.uuid4().hex[:6]}",
            "supplier_type": "manufacturer"}))
        asked = client.post(f"/api/v1/suppliers/{supplier['id']}/ask", json={"question": "Any recalls?"},
                            headers=bearer(team["analyst"]["access_token"]))
        assert asked.status_code == 200, asked.text
        assert client.get("/api/v1/ai/runs", headers=bearer(team["analyst"]["access_token"])).status_code == 403
        runs = client.get("/api/v1/ai/runs", headers=bearer(team["auditor"]["access_token"])).json()["runs"]
        assert len(runs) == 1 and runs[0]["kind"] == "ask" and runs[0]["actor"].startswith("analyst-")
        assert runs[0]["input"]["question"] == "Any recalls?" and runs[0]["status"] == asked.json()["status"]
        detail = client.get(f"/api/v1/ai/runs/{runs[0]['id']}", headers=bearer(team["admin"]["access_token"])).json()["run"]
        assert detail["output"]["note"] == asked.json()["note"] and detail["degraded"] is False
        other = bearer(new_team(("admin",))["admin"]["access_token"])
        assert client.get(f"/api/v1/ai/runs/{runs[0]['id']}", headers=other).status_code == 404
