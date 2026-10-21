"""
Direct SAP connection through the gateway and coordinator, against the fake SAP system
(tests/erp/sap_fake.py). Runs on both backends.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "erp"))
from libs.integrations import sap_odata  # noqa: E402
from sap_fake import FakeSap, order, partner  # noqa: E402

ORG_1 = "a0000000-0000-0000-0000-000000000001"
ORG_2 = "a0000000-0000-0000-0000-000000000002"
PASSWORD = "Comm-User-Pa55word!"
SETTINGS = {"base_url": "https://my-s4.example.com", "sap_client": "100", "username": "SCIRM_COMM", "password": PASSWORD}


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_sap(monkeypatch):
    def install(fake):
        monkeypatch.setattr(sap_odata, "transport_factory", lambda: fake)
        return fake
    return install


@pytest.fixture(scope="module")
def analyst(client, sarah):
    """A fresh analyst in org 1, invited by Sarah."""
    email = f"sap-analyst-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post("/api/v1/org/invitations", json={"email": email, "roles": ["analyst"]},
                          headers=bearer(sarah["access_token"]))
    assert invited.status_code == 200, invited.text
    token = invited.json()["invite_url"].split("#", 1)[1]
    accepted = client.post("/api/v1/invitations/accept",
                           json={"token": token, "name": "SAP Analyst", "password": "Analyst-Passw0rd-123"})
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def connect(client, tokens, **overrides):
    return client.put("/api/v1/integrations/sap", json={**SETTINGS, **overrides}, headers=bearer(tokens["access_token"]))


def numbers(n):
    base = uuid.uuid4().int % 10**8
    return [str(base + i) for i in range(n)]


def suppliers_of(apps, org):
    return asyncio.run(apps["coordinator"].store.list_suppliers(org, limit=None))[0]


def stored_password(apps, org):
    store = apps["coordinator"].store
    if hasattr(store, "erp_connections"):
        return store.erp_connections[(org, "sap")]["password_enc"]
    rows = asyncio.run(store._all(org, "SELECT password_enc FROM erp_connections WHERE system = 'sap'"))
    return rows[0]["password_enc"]


class TestConnectionSettings:
    def test_admin_sets_it_and_the_password_never_comes_back(self, client, sarah, apps):
        r = connect(client, sarah)
        assert r.status_code == 200, r.text
        shown = client.get("/api/v1/integrations/sap", headers=bearer(sarah["access_token"])).json()["connection"]
        assert shown["base_url"] == "https://my-s4.example.com" and shown["username"] == "SCIRM_COMM"
        assert shown["has_password"] is True and "password" not in shown and "password_enc" not in shown
        assert PASSWORD not in r.text and PASSWORD not in json.dumps(shown)
        sealed = stored_password(apps, ORG_1)
        assert sealed.startswith("enc:v1:") and PASSWORD not in sealed

    def test_password_can_be_kept_when_other_settings_change(self, client, sarah, apps):
        connect(client, sarah)
        before = stored_password(apps, ORG_1)
        r = connect(client, sarah, password=None, sap_client="200")
        assert r.status_code == 200 and r.json()["connection"]["sap_client"] == "200"
        assert stored_password(apps, ORG_1) == before
        connect(client, sarah)

    def test_invalid_settings_are_explained(self, client, sarah):
        assert "own fields" in connect(client, sarah, base_url="https://u:p@my-s4.example.com").json()["detail"]
        assert "three digits" in connect(client, sarah, sap_client="1").json()["detail"]
        assert connect(client, sarah, base_url="https://x.example.com/sap/opu/odata/sap/API_X").status_code == 400

    def test_a_new_connection_needs_a_password(self, client, lisa):
        r = connect(client, lisa, password=None)
        assert r.status_code == 400 and "password" in r.json()["detail"]

    def test_only_admins_manage_it(self, client, analyst, auditor):
        assert connect(client, analyst).status_code == 403
        assert connect(client, auditor).status_code == 403
        assert client.post("/api/v1/integrations/sap/test", headers=bearer(analyst["access_token"])).status_code == 403
        assert client.delete("/api/v1/integrations/sap", headers=bearer(auditor["access_token"])).status_code == 403
        # Reading the settings (never the password) is fine for any member.
        assert client.get("/api/v1/integrations/sap", headers=bearer(auditor["access_token"])).status_code == 200

    def test_audit_has_settings_not_the_password(self, client, sarah, apps):
        connect(client, sarah)
        entries = asyncio.run(apps["gateway"].audit_store.list_audit(ORG_1, limit=1000))
        saves = [e for e in entries if e["action"] == "integrations.sap.save"]
        assert saves and all(PASSWORD not in json.dumps(e, default=str) for e in entries)

    def test_connections_belong_to_one_tenant(self, client, sarah, lisa, apps, fake_sap):
        connect(client, sarah)
        other = client.get("/api/v1/integrations/sap", headers=bearer(lisa["access_token"])).json()["connection"]
        assert other is None or other["base_url"] != "https://my-s4.example.com"
        if other is None:
            fake = fake_sap(FakeSap())
            r = client.post("/api/v1/suppliers/import/sap/connection", json={}, headers=bearer(lisa["access_token"]))
            assert r.status_code == 404 and fake.requests == []

    def test_a_password_copied_to_another_connection_does_not_open(self, apps):
        from libs.common import secret_box
        store = apps["coordinator"].store
        sealed = stored_password(apps, ORG_1)
        conn = asyncio.run(store.get_erp_connection(ORG_1, "sap"))
        with pytest.raises(secret_box.SecretBoxError):
            secret_box.decrypt(sealed, f"erp:sap:{ORG_2}:{conn['id']}", allow_plaintext=False)


class TestTest:
    def test_success_and_failure_are_reported_and_remembered(self, client, sarah, fake_sap):
        connect(client, sarah)
        fake_sap(FakeSap())
        ok = client.post("/api/v1/integrations/sap/test", headers=bearer(sarah["access_token"]))
        assert ok.status_code == 200 and ok.json()["ok"] is True, ok.text
        fake_sap(FakeSap(status={"/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV": 403}))
        bad = client.post("/api/v1/integrations/sap/test", headers=bearer(sarah["access_token"])).json()
        assert bad["ok"] is False and "SAP_COM_0053" in json.dumps(bad)
        shown = client.get("/api/v1/integrations/sap", headers=bearer(sarah["access_token"])).json()["connection"]
        assert shown["last_test"]["ok"] is False

    def test_private_addresses_are_refused_outside_development(self, client, sarah, fake_sap, monkeypatch):
        connect(client, sarah)
        fake = fake_sap(FakeSap())
        monkeypatch.setattr(sap_odata, "STRICT", True)
        monkeypatch.setattr(sap_odata, "resolve", lambda host, port: ["10.20.30.40"])
        result = client.post("/api/v1/integrations/sap/test", headers=bearer(sarah["access_token"])).json()
        assert result["ok"] is False and "private" in json.dumps(result) and fake.requests == []
        assert "https" in connect(client, sarah, base_url="http://my-s4.example.com").json()["detail"]


class TestImports:
    def test_supplier_preview_then_apply(self, client, sarah, analyst, apps, fake_sap):
        connect(client, sarah)
        a, b = numbers(2)
        # Business partner numbers deliberately differ from the supplier numbers.
        fake_sap(FakeSap([partner(f"9{a}", a.zfill(10), f"Connector Test {a} GmbH", "JP", "Kobe"),
                          partner(f"9{b}", b, f"Connector Test {b} AG", "DE", "Hamburg", posting_block=True)]))
        preview = client.post("/api/v1/suppliers/import/sap/connection", json={},
                              headers=bearer(analyst["access_token"]))
        assert preview.status_code == 200, preview.text
        assert preview.json()["applied"] is False and preview.json()["source"] == "connection"
        assert not any(s.get("sap_supplier_number") == a for s in suppliers_of(apps, ORG_1))
        applied = client.post("/api/v1/suppliers/import/sap/connection", json={"apply": True},
                              headers=bearer(analyst["access_token"])).json()
        assert applied["written"] >= 2
        by = {s.get("sap_supplier_number"): s for s in suppliers_of(apps, ORG_1)}
        assert by[a]["supplier_code"] == f"SAP-{a}" and by[a]["country_code"] == "JP"
        assert by[a]["sites"][0]["city"] == "Kobe" and by[b]["is_active"] is False

    def test_a_file_import_and_the_connection_update_the_same_suppliers(self, client, sarah, apps, fake_sap):
        connect(client, sarah)
        (n,) = numbers(1)
        lfa1 = f"LIFNR\tNAME1\tLAND1\n{n.zfill(10)}\tSame Supplier {n} GmbH\tDE\n"
        assert client.post("/api/v1/suppliers/import/sap", json={"content": lfa1, "apply": True},
                           headers=bearer(sarah["access_token"])).status_code == 200
        fake_sap(FakeSap([partner(f"7{n}", n, f"Same Supplier {n} GmbH", "AT", "Wien")]))
        client.post("/api/v1/suppliers/import/sap/connection", json={"apply": True},
                    headers=bearer(sarah["access_token"]))
        matches = [s for s in suppliers_of(apps, ORG_1) if s.get("sap_supplier_number") == n]
        assert len(matches) == 1 and matches[0]["country_code"] == "AT"

    def test_spend_from_the_connection(self, client, sarah, apps, fake_sap):
        connect(client, sarah)
        a, b = numbers(2)
        fake_sap(FakeSap([partner(f"8{a}", a, f"Spend Conn {a} GmbH"), partner(f"8{b}", b, f"Spend Conn {b} GmbH")]))
        client.post("/api/v1/suppliers/import/sap/connection", json={"apply": True}, headers=bearer(sarah["access_token"]))
        from datetime import date, timedelta
        recent = (date.today() - timedelta(days=30)).isoformat()
        fake_sap(FakeSap(orders=[order("4500000001", a, recent, [{"NetAmount": "900.00", "NetPriceAmount": "9",
                                                                  "OrderQuantity": "100"}]),
                                 order("4500000002", b, recent, [{"NetAmount": "100.00", "NetPriceAmount": "1",
                                                                  "OrderQuantity": "100"}])]))
        r = client.post("/api/v1/suppliers/import/sap-spend/connection", json={"apply": True},
                        headers=bearer(sarah["access_token"]))
        assert r.status_code == 200, r.text
        assert r.json()["period"]["to"] == date.today().isoformat()
        by = {s.get("sap_supplier_number"): s for s in suppliers_of(apps, ORG_1)}
        assert by[a]["spend_12m"] == {"EUR": "900.00"} and by[a]["spend_rank"] < by[b]["spend_rank"]

    def test_a_failed_read_writes_nothing_and_is_explained(self, client, sarah, apps, fake_sap, monkeypatch):
        connect(client, sarah)
        monkeypatch.setattr(sap_odata, "SUPPLIER_PAGE", 1)
        (n,) = numbers(1)
        fake_sap(FakeSap([partner("1", n, f"Never Written {n} GmbH"), partner("2", "x" + n, "Other GmbH")],
                         fail_after_pages=1))
        r = client.post("/api/v1/suppliers/import/sap/connection", json={"apply": True, "deactivate_missing": True},
                        headers=bearer(sarah["access_token"]))
        assert r.status_code == 502 and "HTTP 500" in r.json()["detail"] and "internal" not in r.json()["detail"]
        assert not any(s.get("sap_supplier_number") == n for s in suppliers_of(apps, ORG_1))
        shown = client.get("/api/v1/integrations/sap", headers=bearer(sarah["access_token"])).json()["connection"]
        assert shown["last_import"]["ok"] is False and shown["last_import"]["kind"] == "suppliers"

    def test_read_only_roles_cannot_import(self, client, auditor):
        assert client.post("/api/v1/suppliers/import/sap/connection", json={},
                           headers=bearer(auditor["access_token"])).status_code == 403
        assert client.post("/api/v1/suppliers/import/sap-spend/connection", json={},
                           headers=bearer(auditor["access_token"])).status_code == 403

    def test_audit_records_connection_imports_with_counts_only(self, client, sarah, apps, fake_sap):
        connect(client, sarah)
        (n,) = numbers(1)
        fake_sap(FakeSap([partner("1", n, f"Audit Conn {n} GmbH")]))
        client.post("/api/v1/suppliers/import/sap/connection", json={"apply": True}, headers=bearer(sarah["access_token"]))
        entries = asyncio.run(apps["gateway"].audit_store.list_audit(ORG_1, limit=1000))
        entry = next(e for e in entries if e["action"] == "suppliers.import.sap"
                     and (e.get("details") or {}).get("source") == "connection")
        assert f"Audit Conn {n}" not in json.dumps(entry, default=str)


def test_removing_the_connection_deletes_the_password(client, sarah, apps):
    connect(client, sarah)
    assert client.delete("/api/v1/integrations/sap", headers=bearer(sarah["access_token"])).status_code == 200
    assert client.get("/api/v1/integrations/sap", headers=bearer(sarah["access_token"])).json()["connection"] is None
    assert asyncio.run(apps["coordinator"].store.get_erp_connection(ORG_1, "sap", with_password=True)) is None
    assert client.delete("/api/v1/integrations/sap", headers=bearer(sarah["access_token"])).status_code == 404


def test_the_old_global_erp_endpoints_are_gone(client, sarah):
    for method, path in (("get", "/api/v1/erp/status"), ("post", "/api/v1/erp/sync"), ("get", "/api/v1/erp/suppliers")):
        assert getattr(client, method)(path, headers=bearer(sarah["access_token"])).status_code in (404, 405)
