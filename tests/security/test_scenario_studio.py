"""
Scenario studio: spend at risk from real spend per currency and the supplier's own stock
answer, for suppliers chosen by list, country, incident or public record; saved scenarios;
tenancy and roles. Not a sample feature. Runs on both backends.
"""

import asyncio
import uuid

from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def org_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["org_id"]


def supplier(apps, org, name, **extra):
    return str(asyncio.run(apps["gateway"].audit_store.create_supplier(org, {
        "name": name, "supplier_code": f"SC-{uuid.uuid4().hex[:6]}", "supplier_type": "manufacturer",
        "spend_main_currency": "EUR", **extra}))["id"])


def answer_stock(client, admin, supplier_id, weeks, single_source="no"):
    """The supplier states its safety stock in a continuity questionnaire, through the portal."""
    sent = client.post("/api/v1/assessments", json={"supplier_id": supplier_id, "template_id": "builtin:continuity",
                                                    "recipient_email": "qa@supplier.example.com"}, headers=admin).json()
    token = sent["portal_url"].split("#", 1)[1]
    answers = {"bcp": "yes", "single_site": "no", "single_source": single_source, "disruption": "no",
               "safety_stock_weeks": str(weeks)}
    done = client.post("/api/v1/portal/assessment/submit", headers={"X-Portal-Token": token},
                       json={"answers": answers, "name": "QA", "email": "qa@supplier.example.com"})
    assert done.status_code == 200, done.text


def run(client, headers, **definition):
    response = client.post("/api/v1/scenario-studio/run", json=definition, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


class TestRun:
    def test_spend_at_risk_uses_real_spend_and_the_suppliers_stock_answer(self, client, apps, new_team):
        team = new_team(("admin", "viewer"))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        alpha = supplier(apps, org, "Alpha API", spend_12m={"EUR": "5200"}, country_code="IN")
        supplier(apps, org, "Beta US", spend_12m={"USD": "520"}, country_code="US")
        answer_stock(client, admin, alpha, 2, single_source="yes")
        result = run(client, bearer(team["viewer"]["access_token"]), duration_weeks=4)
        assert result["main_currency"] == "EUR" and result["scope"] == "All active suppliers"
        assert result["interrupted"] == {"EUR": "400.00", "USD": "40.00"}
        assert result["at_risk"] == {"EUR": "200.00", "USD": "40.00"}
        a = result["suppliers"]["ranked"][0]
        assert a["coverage_weeks"] == 2.0 and a["coverage_source"].startswith("supplier-provided: Supply continuity")
        assert a["single_source"] is True
        assert result["suppliers"]["other_currencies"][0]["coverage_source"].startswith("unknown")
        assert [m["kind"] for m in result["plan"]["ranked"]] == ["safety_stock", "second_source"]

    def test_scopes_country_suppliers_and_incident(self, client, apps, new_team):
        team, other = new_team(("admin",)), new_team(("admin",))
        org, admin = org_of(team["admin"]), bearer(team["admin"]["access_token"])
        india = supplier(apps, org, "Pune Pharma", spend_12m={"EUR": "5200"}, country_code="IN")
        supplier(apps, org, "Lyon Labs", spend_12m={"EUR": "10400"}, country_code="FR",
                 sites=[{"label": "Hyderabad plant", "country": "IN"}])
        supplier(apps, org, "Texas Tubes", spend_12m={"EUR": "1"}, country_code="US")
        by_country = run(client, admin, scope={"type": "country", "country": "in"}, duration_weeks=4)
        assert sorted(s["name"] for s in by_country["suppliers"]["ranked"]) == ["Lyon Labs", "Pune Pharma"]
        chosen = run(client, admin, scope={"type": "suppliers", "supplier_ids": [india]}, duration_weeks=52)
        assert chosen["at_risk"] == {"EUR": "5200.00"}
        theirs = supplier(apps, org_of(other["admin"]), "Not Ours", spend_12m={"EUR": "1"})
        assert client.post("/api/v1/scenario-studio/run", json={"scope": {"type": "suppliers", "supplier_ids": [theirs]}},
                           headers=admin).status_code == 404
        incident = client.post("/api/v1/incidents", json={"title": "Monsoon", "supplier_ids": [india]}, headers=admin).json()
        by_incident = run(client, admin, scope={"type": "incident", "incident_id": incident["incident"]["id"]})
        assert [s["supplier_id"] for s in by_incident["suppliers"]["ranked"]] == [india]
        assert client.post("/api/v1/scenario-studio/run", json={"duration_weeks": 53}, headers=admin).status_code == 422

    def test_it_is_not_a_sample_feature(self, apps):
        gateway = apps["gateway"]
        assert gateway._is_sample_feature("/api/v1/scenarios/simulate")
        assert not gateway._is_sample_feature("/api/v1/scenario-studio/run")


class TestSaved:
    def test_save_run_delete_with_roles_and_tenancy(self, client, apps, new_team):
        team, other = new_team(("admin", "viewer")), new_team(("admin",))
        org, admin, viewer = org_of(team["admin"]), bearer(team["admin"]["access_token"]), bearer(team["viewer"]["access_token"])
        supplier(apps, org, "Saved Supplier", spend_12m={"EUR": "5200"}, country_code="DE")
        definition = {"scope": {"type": "country", "country": "DE"}, "duration_weeks": 4}
        assert client.post("/api/v1/scenario-studio/saved", json={"name": "Germany out", "definition": definition},
                           headers=viewer).status_code == 403
        saved = client.post("/api/v1/scenario-studio/saved", json={"name": "Germany out", "definition": definition},
                            headers=admin).json()["scenario"]
        ran = client.get(f"/api/v1/scenario-studio/saved/{saved['id']}/run", headers=viewer).json()
        assert ran["scenario"]["name"] == "Germany out" and ran["result"]["at_risk"] == {"EUR": "400.00"}
        stranger = bearer(other["admin"]["access_token"])
        assert client.get(f"/api/v1/scenario-studio/saved/{saved['id']}/run", headers=stranger).status_code == 404
        assert client.get("/api/v1/scenario-studio/saved", headers=stranger).json()["scenarios"] == []
        assert client.delete(f"/api/v1/scenario-studio/saved/{saved['id']}", headers=stranger).status_code == 404
        assert client.delete(f"/api/v1/scenario-studio/saved/{saved['id']}", headers=admin).status_code == 200
