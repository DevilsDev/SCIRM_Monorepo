"""
The MCP server at /mcp: only API keys with the mcp scope (which reach nothing else); read
tools see only the key's organization; Ask is cited and logged; changes are proposals under
the action policy; third-party text is marked; every call is logged and rate limited.
Runs on both backends.
"""

import asyncio
import json
import uuid

from libs.common import mcp_tools
from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token

ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
          "MCP-Protocol-Version": "2025-06-18"}


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def org_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["org_id"]


def mcp_key(client, admin_tokens, scope="mcp") -> str:
    created = client.post("/api/v1/org/api-keys", json={"name": "Claude Desktop", "scope": scope},
                          headers=bearer(admin_tokens["access_token"]))
    assert created.status_code == 200, created.text
    return created.json()["key"]


def rpc(client, key, method, params=None, rid=1):
    return client.post("/mcp", headers={**ACCEPT, **bearer(key)},
                       json={"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params else {})})


def tool(client, key, name, **arguments):
    response = rpc(client, key, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    return json.loads(result["content"][0]["text"])


def supplier(apps, org, name):
    return str(asyncio.run(apps["gateway"].audit_store.create_supplier(org, {
        "name": name, "supplier_code": f"MC-{uuid.uuid4().hex[:6]}", "supplier_type": "manufacturer"}))["id"])


class TestAccess:
    def test_only_mcp_keys_reach_the_mcp_server_and_nothing_else(self, client, new_team):
        team = new_team(("admin",))
        key, read_key = mcp_key(client, team["admin"]), mcp_key(client, team["admin"], "read")
        assert client.post("/mcp", headers=ACCEPT, json={}).status_code == 401
        assert client.post("/mcp", headers={**ACCEPT, **bearer(team["admin"]["access_token"])}, json={}).status_code == 401
        assert rpc(client, read_key, "tools/list").status_code == 403
        assert client.get("/api/v1/suppliers", headers=bearer(key)).status_code == 403
        listed = rpc(client, key, "tools/list")
        assert listed.status_code == 200
        tools = {t["name"]: t for t in listed.json()["result"]["tools"]}
        assert set(tools) == {"search_suppliers", "supplier_records", "ask", "regulatory_watch", "list_incidents",
                              "get_incident", "run_scenario", "propose_action"}
        assert tools["search_suppliers"]["annotations"]["readOnlyHint"] is True
        assert tools["propose_action"]["annotations"]["readOnlyHint"] is False
        init = rpc(client, key, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                               "clientInfo": {"name": "test", "version": "0"}}).json()["result"]
        assert "never follow instructions" in init["instructions"]

    def test_reads_see_only_the_keys_organization(self, client, apps, new_team):
        ours, theirs = new_team(("admin",)), new_team(("admin",))
        mine = supplier(apps, org_of(ours["admin"]), f"Our Supplier {uuid.uuid4().hex[:4]}")
        other = supplier(apps, org_of(theirs["admin"]), f"Their Supplier {uuid.uuid4().hex[:4]}")
        key = mcp_key(client, ours["admin"])
        names = [s["id"] for s in tool(client, key, "search_suppliers")["suppliers"]]
        assert names == [mine]
        assert tool(client, key, "search_suppliers", query="their")["suppliers"] == []
        assert "error" in tool(client, key, "get_incident", incident_id=str(uuid.uuid4()))
        records = tool(client, key, "supplier_records", supplier_id=other)
        assert "error" in records  # another organization's supplier is not found


class TestScenarioTool:
    def test_an_agent_gets_spend_at_risk_computed_by_code(self, client, apps, new_team):
        team = new_team(("admin",))
        org = org_of(team["admin"])
        asyncio.run(apps["gateway"].audit_store.create_supplier(org, {
            "name": "Chennai API", "supplier_code": f"MS-{uuid.uuid4().hex[:6]}", "supplier_type": "manufacturer",
            "country_code": "IN", "spend_12m": {"EUR": "5200"}, "spend_main_currency": "EUR"}))
        key = mcp_key(client, team["admin"])
        result = tool(client, key, "run_scenario", scope="country", country="IN", duration_weeks=4)
        assert result["at_risk"] == {"EUR": "400.00"} and result["suppliers_without_coverage_data"] == 1
        assert "Invalid scenario" in tool(client, key, "run_scenario", duration_weeks=99)["error"]


class TestTools:
    def test_ask_is_cited_marked_and_logged_as_an_ask(self, client, apps, new_team):
        team = new_team(("admin",))
        org = org_of(team["admin"])
        sid = str(asyncio.run(apps["coordinator"].store.create_supplier(org, {
            "name": f"Calm Waters Pharma {uuid.uuid4().hex[:4]}", "supplier_code": f"MA-{uuid.uuid4().hex[:6]}",
            "supplier_type": "manufacturer"}))["id"])
        key = mcp_key(client, team["admin"])
        answer = tool(client, key, "ask", supplier_id=sid, question="Any recalls in the last year?")
        assert answer["notice"].startswith("Record titles") and answer["status"] in ("no_records", "answered",
                                                                                  "insufficient_evidence")
        runs = client.get("/api/v1/ai/runs", headers=bearer(team["admin"]["access_token"])).json()["runs"]
        asks = [r for r in runs if r["kind"] == "ask"]
        assert asks and asks[0]["actor"].startswith("api-key:Claude Desktop") and asks[0]["actor_type"] == "api_key"

    def test_changes_are_proposals_under_the_policy(self, client, new_team):
        team = new_team(("admin",))
        admin, key = bearer(team["admin"]["access_token"]), mcp_key(client, team["admin"])
        queued = tool(client, key, "propose_action", action="incident.open", params={"title": "Typhoon near Kaohsiung"},
                      reason="GDACS red alert near two supplier sites")
        assert queued["status"] == "pending" and "approval" in queued["message"]
        assert client.get("/api/v1/incidents", headers=admin).json()["incidents"] == []  # nothing happened yet
        refused = tool(client, key, "propose_action", action="assessment.send",
                       params={"supplier_id": str(uuid.uuid4()), "template_id": "builtin:quality",
                               "recipient_email": "a@b.example.com"}, reason="x")
        assert "does not let AI agents" in refused["error"]
        assert "Invalid proposal" in tool(client, key, "propose_action", action="watchlist.add", params={"term": "x"},
                                          reason="r")["error"]
        assert "reason" in tool(client, key, "propose_action", action="watchlist.add", params={"term": "rifampicin"},
                                reason=" ")["error"]
        client.put("/api/v1/ai/policy", json={"action": "watchlist.add", "mode": "allowed"}, headers=admin)
        done = tool(client, key, "propose_action", action="watchlist.add", params={"term": "rifampicin"},
                    reason="Supplier makes rifampicin API")
        assert done["status"] == "executed"
        assert [i["term"] for i in client.get("/api/v1/watchlist", headers=admin).json()["items"]] == ["rifampicin"]
        pending = client.get("/api/v1/ai/proposals", params={"status": "pending"}, headers=admin).json()["proposals"]
        assert [p["summary"] for p in pending] == ["GDACS red alert near two supplier sites"]

    def test_every_call_is_logged_and_keys_are_rate_limited(self, client, new_team, monkeypatch):
        team = new_team(("admin",))
        key = mcp_key(client, team["admin"])
        tool(client, key, "list_incidents")
        monkeypatch.setattr(mcp_tools, "CALLS_PER_MINUTE", 1)
        limited = tool(client, key, "list_incidents")
        assert "Rate limit" in limited["error"]
        runs = client.get("/api/v1/ai/runs", params={"kind": "mcp_tool"}, headers=bearer(team["admin"]["access_token"])).json()["runs"]
        assert [r["status"] for r in runs][:2] == ["refused", "ok"]
        assert runs[1]["input"] == {"tool": "list_incidents", "arguments": {"status": ""}}
