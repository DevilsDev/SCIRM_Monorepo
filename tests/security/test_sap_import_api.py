"""
SAP supplier import through the gateway and coordinator. Runs on both backends
(STORE_BACKEND=memory and postgres), like the rest of the security suite.
"""

import asyncio
import uuid

import pytest

ORG_1 = "a0000000-0000-0000-0000-000000000001"
ORG_2 = "a0000000-0000-0000-0000-000000000002"
URL = "/api/v1/suppliers/import/sap"
HEADER = "LIFNR\tNAME1\tNAME2\tLAND1\tSPERR\tLOEVM"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def extract(*rows):
    return "\n".join([HEADER, *("\t".join(r) for r in rows)]) + "\n"


def numbered():
    """A supplier number no other test uses (the suite shares one store)."""
    return str(uuid.uuid4().int % 10**9).zfill(10)


def post(client, tokens, content, **kw):
    return client.post(URL, json={"content": content, **kw}, headers=bearer(tokens["access_token"]))


def suppliers(apps, org):
    store = apps["coordinator"].store  # suppliers belong to the coordinator
    return asyncio.run(store.list_suppliers(org, limit=None))[0]


def by_number(apps, org, number):
    number = number.lstrip("0")
    return [s for s in suppliers(apps, org) if s.get("sap_supplier_number") == number]


class TestImport:
    def test_preview_writes_nothing_and_apply_writes(self, client, sarah, apps):
        n = numbered()
        content = extract([n, "Preview Pharma GmbH", "Preview Holdings AG", "DE", "", ""])
        preview = post(client, sarah, content)
        assert preview.status_code == 200, preview.text
        assert preview.json()["applied"] is False and preview.json()["summary"] == {"create": 1}
        assert by_number(apps, ORG_1, n) == []
        applied = post(client, sarah, content, apply=True)
        assert applied.json()["written"] == 1
        [s] = by_number(apps, ORG_1, n)
        assert s["supplier_code"] == f"SAP-{n.lstrip('0')}" and s["country_code"] == "DE"
        assert s["aliases"] == ["Preview Holdings AG"]

    def test_reimport_is_unchanged_and_keeps_manual_aliases(self, client, sarah, apps):
        n = numbered()
        content = extract([n, "Alias Pharma GmbH", "", "FR", "", ""])
        post(client, sarah, content, apply=True)
        [s] = by_number(apps, ORG_1, n)
        edited = client.put(f"/api/v1/suppliers/{s['id']}", json={"aliases": ["Alias Europe"]},
                            headers=bearer(sarah["access_token"]))
        assert edited.status_code == 200, edited.text
        again = post(client, sarah, extract([n.lstrip("0"), "Alias Pharma GmbH", "Alias Labs Ltd", "FR", "", ""]), apply=True)
        assert again.json()["summary"] == {"update": 1}
        [s] = by_number(apps, ORG_1, n)
        assert s["aliases"] == ["Alias Europe", "Alias Labs Ltd"]
        assert post(client, sarah, extract([n, "Alias Pharma GmbH", "", "FR", "", ""])).json()["summary"] == {"unchanged": 1}

    def test_a_name_clash_waits_for_a_decision(self, client, sarah, apps):
        name = f"Clash {uuid.uuid4().hex[:6]} GmbH"
        manual = client.post("/api/v1/suppliers", json={"name": name, "supplier_code": f"SUP-{uuid.uuid4().hex[:6]}"},
                             headers=bearer(sarah["access_token"])).json()
        n = numbered()
        content = extract([n, name, "", "DE", "", ""])
        preview = post(client, sarah, content).json()
        assert preview["summary"] == {"needs_decision": 1} and preview["duplicates"][0]["existing_id"] == manual["id"]
        assert post(client, sarah, content, apply=True).json()["written"] == 0
        linked = post(client, sarah, content, apply=True, decisions={n.lstrip("0"): f"link:{manual['id']}"}).json()
        assert linked["summary"] == {"link": 1}
        [s] = by_number(apps, ORG_1, n)
        assert s["id"] == manual["id"] and s["supplier_code"] == manual["supplier_code"]

    def test_a_taken_supplier_code_does_not_break_the_import(self, client, sarah, apps):
        """A supplier entered by hand with code SAP-<n>: no unique-constraint failure mid-import."""
        n = numbered().lstrip("0")
        manual = client.post("/api/v1/suppliers", json={"name": f"Hand Entered {n} Ltd", "supplier_code": f"SAP-{n}"},
                             headers=bearer(sarah["access_token"]))
        assert manual.status_code == 200, manual.text
        other = numbered()
        result = post(client, sarah, extract([n, "Different Name GmbH", "", "DE", "", ""],
                                             [other, "Fine Supplier GmbH", "", "DE", "", ""]), apply=True)
        assert result.status_code == 200, result.text
        assert result.json()["summary"] == {"needs_decision": 1, "create": 1} and result.json()["written"] == 1

    def test_a_failed_batch_writes_nothing(self, apps):
        store = apps["coordinator"].store
        name = f"Atomic {uuid.uuid4().hex[:6]} GmbH"
        with pytest.raises(KeyError):
            asyncio.run(store.write_suppliers(ORG_1, [{"name": name, "supplier_code": f"SAP-{uuid.uuid4().hex[:6]}"}],
                                              [(str(uuid.uuid4()), {"name": "nobody"})]))
        assert not any(s.get("name") == name for s in suppliers(apps, ORG_1))

    def test_bad_files_are_a_clear_400(self, client, sarah):
        response = post(client, sarah, "Vendor,Company\n1,Acme\n")
        assert response.status_code == 400 and "LIFNR" in response.json()["detail"]


class TestAccess:
    def test_read_only_roles_cannot_import(self, client, auditor):
        assert post(client, auditor, extract(["1", "Acme GmbH", "", "DE", "", ""])).status_code == 403

    def test_imports_stay_in_the_callers_org(self, client, lisa, apps):
        n = numbered()
        post(client, lisa, extract([n, "Org Two Supplier GmbH", "", "JP", "", ""]), apply=True)
        assert len(by_number(apps, ORG_2, n)) == 1 and by_number(apps, ORG_1, n) == []

    def test_cannot_link_to_another_orgs_supplier(self, client, lisa, apps):
        org1_supplier = suppliers(apps, ORG_1)[0]
        n = numbered()
        result = post(client, lisa, extract([n, "Linker GmbH", "", "JP", "", ""]), apply=True,
                      decisions={n.lstrip("0"): f"link:{org1_supplier['id']}"}).json()
        assert result["summary"] == {"skip": 1} and result["written"] == 0
        assert not any(s.get("sap_supplier_number") == n.lstrip("0") for s in suppliers(apps, ORG_1))

    def test_the_audit_log_has_counts_not_contents(self, client, sarah, apps):
        n = numbered()
        post(client, sarah, extract([n, "Audited Secret Supplier GmbH", "", "DE", "", ""]), apply=True)
        log = client.get("/api/v1/audit?limit=20", headers=bearer(sarah["access_token"])).json()["entries"]
        entry = next(e for e in log if e["action"] == "suppliers.import.sap")
        assert entry["details"]["written"] == 1
        assert "Audited Secret Supplier" not in str(log)
