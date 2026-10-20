"""
No rating nobody made: a supplier's risk score and tier are only shown once an assessment
recorded one. Stored defaults (50 / medium) and demo seed values never read as a rating.
Runs on both backends, like the rest of the security suite.
"""

import uuid


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_unassessed_suppliers_have_no_score(client, sarah):
    suppliers = client.get("/api/v1/suppliers?limit=200", headers=bearer(sarah["access_token"])).json()["suppliers"]
    assert suppliers
    assert all(s["risk_score"] is None and s["risk_tier"] is None for s in suppliers)


def test_clients_cannot_set_a_score(client, sarah):
    created = client.post("/api/v1/suppliers", json={"name": f"Scored {uuid.uuid4().hex[:6]} Ltd", "risk_score": 12,
                                                     "risk_tier": "low", "risk_assessed_at": "2026-01-01"},
                          headers=bearer(sarah["access_token"]))
    assert created.status_code == 200, created.text
    assert created.json()["risk_score"] is None and created.json()["risk_tier"] is None
    updated = client.put(f"/api/v1/suppliers/{created.json()['id']}", json={"risk_score": 99, "risk_tier": "high"},
                         headers=bearer(sarah["access_token"]))
    assert updated.json()["risk_score"] is None


def test_the_tier_filter_matches_what_is_shown(client, sarah):
    body = client.get("/api/v1/suppliers?risk_tier=medium", headers=bearer(sarah["access_token"])).json()
    assert body["suppliers"] == [] and body["total"] == 0


def test_demo_suppliers_are_marked(client, sarah):
    suppliers = client.get("/api/v1/suppliers?limit=200", headers=bearer(sarah["access_token"])).json()["suppliers"]
    seeded = [s for s in suppliers if s.get("supplier_code") in ("SUP-ALPHA", "SUP-BETA", "SUP-GAMMA")]
    assert len(seeded) == 3 and all(s.get("demo_note") for s in seeded)


def test_the_supply_chain_map_shows_no_placeholder_scores(client, sarah):
    response = client.get("/api/v1/supply-chain/map", headers=bearer(sarah["access_token"]))
    assert response.status_code == 200, response.text
    nodes = [n for n in response.json().get("nodes", []) if n.get("type") == "supplier"]
    assert nodes and all(n["risk_score"] is None for n in nodes)
