"""
Supplier ownership from GLEIF through the gateway and coordinator, on recorded GLEIF
responses (tests/gleif_support.py). Runs on both backends.
"""

import uuid

from gleif_support import BRAINE, GROUP, VERVIERS


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def new_supplier(client, tokens, name="Lonza Verviers", **extra):
    body = {"name": f"{name} {uuid.uuid4().hex[:4]}", "supplier_code": f"OWN-{uuid.uuid4().hex[:6]}", **extra}
    r = client.post("/api/v1/suppliers", json=body, headers=bearer(tokens["access_token"]))
    assert r.status_code == 200, r.text
    return r.json()


def link(client, tokens, supplier_id, lei):
    return client.put(f"/api/v1/suppliers/{supplier_id}/ownership", json={"lei": lei}, headers=bearer(tokens["access_token"]))


class TestOwnership:
    def test_search_link_and_show_parents(self, client, sarah):
        s = new_supplier(client, sarah, country_code="BE")
        found = client.get("/api/v1/ownership/search", params={"name": "Lonza", "country": "BE"},
                           headers=bearer(sarah["access_token"])).json()
        assert VERVIERS in [c["lei"] for c in found["candidates"]] and found["source"]["licence"] == "CC0 1.0"
        before = client.get(f"/api/v1/suppliers/{s['id']}/ownership", headers=bearer(sarah["access_token"])).json()
        assert before["link"] is None
        r = link(client, sarah, s["id"], VERVIERS)
        assert r.status_code == 200, r.text
        got = client.get(f"/api/v1/suppliers/{s['id']}/ownership", headers=bearer(sarah["access_token"])).json()["link"]
        assert got["lei"] == VERVIERS and got["confirmed_by"] == "sarah.chen@pharmacorp.com"
        assert got["snapshot"]["ultimate_parent"]["lei"] == GROUP

    def test_link_is_audited_and_can_be_removed(self, client, sarah):
        s = new_supplier(client, sarah)
        assert link(client, sarah, s["id"], BRAINE).status_code == 200
        removed = client.delete(f"/api/v1/suppliers/{s['id']}/ownership", headers=bearer(sarah["access_token"]))
        assert removed.status_code == 200
        assert client.delete(f"/api/v1/suppliers/{s['id']}/ownership", headers=bearer(sarah["access_token"])).status_code == 404
        log = client.get("/api/v1/audit", params={"limit": 50}, headers=bearer(sarah["access_token"])).json()["entries"]
        linked = next(e for e in log if e["action"] == "ownership.linked" and e.get("resource_id") == s["id"])
        assert "LONZA BRAINE SA" in str(linked.get("details"))
        assert any(e["action"] == "ownership.unlinked" and e.get("resource_id") == s["id"] for e in log)

    def test_bad_or_unknown_lei(self, client, sarah):
        s = new_supplier(client, sarah)
        assert link(client, sarah, s["id"], "529900T8BM49AURSDO55").status_code == 400  # not in GLEIF
        assert link(client, sarah, s["id"], "NOT-AN-LEI-123456789").status_code == 400
        assert link(client, sarah, s["id"], "short").status_code == 422

    def test_gleif_outage_is_a_503_and_changes_nothing(self, client, sarah, apps):
        s = new_supplier(client, sarah)
        apps["gleif_state"]["down"] = True
        try:
            assert link(client, sarah, s["id"], VERVIERS).status_code == 503
            assert client.get("/api/v1/ownership/search", params={"name": "Lonza"},
                              headers=bearer(sarah["access_token"])).status_code == 503
        finally:
            apps["gleif_state"]["down"] = False
        assert client.get(f"/api/v1/suppliers/{s['id']}/ownership",
                          headers=bearer(sarah["access_token"])).json()["link"] is None

    def test_read_only_roles_and_other_tenants(self, client, new_team, lisa):
        team = new_team(("admin", "viewer"))
        viewer = team["viewer"]
        s = new_supplier(client, team["admin"])
        assert link(client, viewer, s["id"], VERVIERS).status_code == 403
        assert client.get("/api/v1/ownership/search", params={"name": "Lonza"},
                          headers=bearer(viewer["access_token"])).status_code == 403
        assert client.get(f"/api/v1/suppliers/{s['id']}/ownership", headers=bearer(viewer["access_token"])).status_code == 200
        assert link(client, lisa, s["id"], VERVIERS).status_code == 404
        assert client.get(f"/api/v1/suppliers/{s['id']}/ownership", headers=bearer(lisa["access_token"])).status_code == 404

    def test_overview_groups_shared_owners_and_lists_unknowns(self, client, new_team):
        team = new_team(("admin", "viewer"))
        admin = team["admin"]
        verviers, group = new_supplier(client, admin), new_supplier(client, admin, name="Lonza Group")
        braine, unlinked = new_supplier(client, admin, name="Lonza Braine"), new_supplier(client, admin, name="Acme")
        for supplier, lei in ((verviers, VERVIERS), (group, GROUP), (braine, BRAINE)):
            assert link(client, admin, supplier["id"], lei).status_code == 200
        body = client.get("/api/v1/ownership", headers=bearer(team["viewer"]["access_token"])).json()
        assert len(body["links"]) == 3
        [shared] = body["shared_owners"]
        assert shared["owner_lei"] == GROUP
        assert sorted(s["supplier_id"] for s in shared["suppliers"]) == sorted([verviers["id"], group["id"]])
        assert [u["supplier_id"] for u in body["unlinked"]] == [unlinked["id"]]

    def test_refresh(self, client, sarah):
        s = new_supplier(client, sarah)
        assert client.post(f"/api/v1/suppliers/{s['id']}/ownership/refresh",
                           headers=bearer(sarah["access_token"])).status_code == 404
        link(client, sarah, s["id"], VERVIERS)
        r = client.post(f"/api/v1/suppliers/{s['id']}/ownership/refresh", headers=bearer(sarah["access_token"]))
        assert r.status_code == 200 and r.json()["link"]["lei"] == VERVIERS
