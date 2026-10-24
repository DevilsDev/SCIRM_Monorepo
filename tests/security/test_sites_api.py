"""
Supplier sites through the gateway and coordinator, and site-level exposure end to end.
Runs on both backends.
"""

import asyncio
import uuid

ORG_1 = "a0000000-0000-0000-0000-000000000001"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def new_supplier(client, tokens, **extra):
    body = {"name": f"Site Test {uuid.uuid4().hex[:6]} GmbH", "supplier_code": f"SITE-{uuid.uuid4().hex[:6]}", **extra}
    r = client.post("/api/v1/suppliers", json=body, headers=bearer(tokens["access_token"]))
    assert r.status_code == 200, r.text
    return r.json()


def add_site(client, tokens, supplier_id, **site):
    return client.post(f"/api/v1/suppliers/{supplier_id}/sites", json=site, headers=bearer(tokens["access_token"]))


class TestSites:
    def test_add_by_city_by_coordinates_and_remove(self, client, sarah):
        s = new_supplier(client, sarah, country_code="DE")
        by_city = add_site(client, sarah, s["id"], label="Plant Cologne", city="Cologne", country="de")
        assert by_city.status_code == 200, by_city.text
        site = by_city.json()["sites"][0]
        assert site["country"] == "DE" and site["precision"] == "city" and site["source"] == "manual"
        exact = add_site(client, sarah, s["id"], label="Warehouse", country="DE", lat=51.5, lon=7.1).json()["sites"][1]
        assert exact["precision"] == "exact" and exact["lat"] == 51.5
        removed = client.delete(f"/api/v1/suppliers/{s['id']}/sites/{site['id']}", headers=bearer(sarah["access_token"]))
        assert [x["label"] for x in removed.json()["sites"]] == ["Warehouse"]

    def test_bad_input_is_explained(self, client, sarah):
        s = new_supplier(client, sarah)
        unknown = add_site(client, sarah, s["id"], label="X", city="Nowhereville", country="DE")
        assert unknown.status_code == 400 and "coordinates" in unknown.json()["detail"]
        assert add_site(client, sarah, s["id"], label="X", country="DE", lat=51.5).status_code == 400
        assert add_site(client, sarah, s["id"], label="X", country="Germany", city="Berlin").status_code in (400, 422)
        assert add_site(client, sarah, s["id"], label="X", country="DE", lat=95, lon=0).status_code in (400, 422)

    def test_sites_cannot_be_written_directly(self, client, sarah):
        s = new_supplier(client, sarah)
        r = client.put(f"/api/v1/suppliers/{s['id']}", json={"sites": [{"lat": 1, "lon": 1}]},
                       headers=bearer(sarah["access_token"]))
        assert r.status_code == 200 and not r.json().get("sites")

    def test_read_only_roles_and_other_tenants(self, client, sarah, lisa, auditor):
        s = new_supplier(client, sarah)
        assert add_site(client, auditor, s["id"], label="X", city="Berlin", country="DE").status_code == 403
        assert add_site(client, lisa, s["id"], label="X", city="Berlin", country="DE").status_code == 404


class TestExposureEndToEnd:
    def test_alerts_near_a_site_are_exposures_and_others_are_counted(self, client, sarah, apps):
        s = new_supplier(client, sarah, country_code="JP")
        add_site(client, sarah, s["id"], label="Kobe plant", city="Kobe", country="JP")
        tag = uuid.uuid4().hex[:6]
        near = {"source": "gdacs", "external_id": f"EQ-near-{tag}", "signal_type": "disaster", "severity": "high",
                "title": "Earthquake near Kobe", "summary": "", "published_at": "2026-10-20", "country_codes": ["JP"],
                "entity_names": [], "raw": {"eventtype": "EQ", "alertlevel": "Orange", "lat": 34.6, "lon": 135.0}}
        far = {**near, "external_id": f"EQ-far-{tag}", "title": "Earthquake near Tokyo",
               "raw": {**near["raw"], "lat": 35.68, "lon": 139.69}}
        asyncio.run(apps["ingestion"].store.upsert_signals([near, far]))
        body = client.get(f"/api/v1/suppliers/{s['id']}/signals", headers=bearer(sarah["access_token"])).json()
        titles = [m["signal"]["title"] for m in body["exposures"]]
        assert "Earthquake near Kobe" in titles and "Earthquake near Tokyo" not in titles
        kobe = next(m for m in body["exposures"] if m["signal"]["title"] == "Earthquake near Kobe")
        assert kobe["match_type"] == "site_proximity" and kobe["site"]["site"] == "Kobe plant"
        assert body["site_level"] is True and body["exposures_elsewhere"] >= 1
