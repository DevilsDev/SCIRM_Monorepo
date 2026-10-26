"""
Water risk by site through the gateway (WRI Aqueduct 4.0). Runs on both backends.
"""

import uuid


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def new_supplier(client, tokens, **extra):
    body = {"name": f"Water Test {uuid.uuid4().hex[:6]} SAE", "supplier_code": f"WR-{uuid.uuid4().hex[:6]}", **extra}
    r = client.post("/api/v1/suppliers", json=body, headers=bearer(tokens["access_token"]))
    assert r.status_code == 200, r.text
    return r.json()


def add_site(client, tokens, supplier_id, **site):
    r = client.post(f"/api/v1/suppliers/{supplier_id}/sites", json=site, headers=bearer(tokens["access_token"]))
    assert r.status_code == 200, r.text
    return r.json()


class TestWaterRisk:
    def test_supplier_sites_get_wris_indicators(self, client, sarah):
        s = new_supplier(client, sarah)
        add_site(client, sarah, s["id"], label="Cairo plant", country="EG", lat=30.0444, lon=31.2357)
        body = client.get(f"/api/v1/water-risk/suppliers/{s['id']}", headers=bearer(sarah["access_token"])).json()
        assert "sites" in body, body
        site = body["sites"][0]
        assert site["status"] == "inside" and site["province"] == "Al Qahirah"
        bws = next(i for i in site["indicators"] if i["key"] == "bws")
        assert bws["label"] == "Extremely High (>80%)"
        assert body["source"]["licence"] == "CC BY 4.0"

    def test_unknown_or_foreign_supplier(self, client, sarah, lisa):
        s = new_supplier(client, sarah)
        assert client.get(f"/api/v1/water-risk/suppliers/{s['id']}", headers=bearer(lisa["access_token"])).status_code == 404
        assert client.get(f"/api/v1/water-risk/suppliers/{uuid.uuid4()}",
                          headers=bearer(sarah["access_token"])).status_code == 404

    def test_overview_lists_sites_and_names_suppliers_without_one(self, client, new_team):
        team = new_team(("admin", "viewer"))
        admin = team["admin"]
        located = new_supplier(client, admin)
        add_site(client, admin, located["id"], label="Basel", country="CH", lat=47.5596, lon=7.5886)
        add_site(client, admin, located["id"], label="Frankfurt", city="Frankfurt am Main", country="DE")
        bare = new_supplier(client, admin, country_code="IN")
        body = client.get("/api/v1/water-risk", headers=bearer(team["viewer"]["access_token"])).json()
        assert sorted(r["label"] for r in body["sites"]) == ["Basel", "Frankfurt"]
        assert [u["supplier_id"] for u in body["suppliers_without_located_site"]] == [bare["id"]]

    def test_csv_export_carries_the_source_and_is_audited(self, client, new_team):
        team = new_team(("admin",))
        admin = team["admin"]
        s = new_supplier(client, admin, name="=HYPERLINK(\"x\") Ltd", supplier_code=f"WR-{uuid.uuid4().hex[:6]}")
        add_site(client, admin, s["id"], label="Cairo", country="EG", lat=30.0444, lon=31.2357)
        r = client.get("/api/v1/water-risk?format=csv", headers=bearer(admin["access_token"]))
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("supplier,site,") and "bws_label" in lines[0] and "water_stress_bau_2050" in lines[0]
        assert "Extremely High (>80%)" in lines[1] and "WRI Aqueduct 4.0 (CC BY 4.0)" in lines[1]
        assert lines[1].startswith("\"'=HYPERLINK") and ",EG," in lines[1]
        entries = client.get("/api/v1/audit", params={"limit": 50}, headers=bearer(admin["access_token"])).json()["entries"]
        assert any(e.get("action") == "water_risk.exported" for e in entries)

    def test_bad_format(self, client, sarah):
        assert client.get("/api/v1/water-risk?format=xml", headers=bearer(sarah["access_token"])).status_code == 400

    def test_needs_a_sign_in(self, client):
        assert client.get("/api/v1/water-risk").status_code in (401, 403)
        assert client.get("/api/v1/water-risk/catalog").status_code in (401, 403)
