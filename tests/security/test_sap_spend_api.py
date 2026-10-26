"""
Purchase-order spend import through the gateway and coordinator. Runs on both backends.
"""

import asyncio
import uuid

ORG_1 = "a0000000-0000-0000-0000-000000000001"
ORG_2 = "a0000000-0000-0000-0000-000000000002"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def numbers(n):
    base = uuid.uuid4().int % 10**8
    return [str(base + i) for i in range(n)]


def vendors(client, tokens, nums):
    lfa1 = "LIFNR\tNAME1\tLAND1\n" + "".join(f"{n}\tSpend Test {n} GmbH\tDE\n" for n in nums)
    r = client.post("/api/v1/suppliers/import/sap", json={"content": lfa1, "apply": True}, headers=bearer(tokens["access_token"]))
    assert r.status_code == 200, r.text


def orders(*rows):
    return "EBELN\tLIFNR\tBEDAT\tNETWR\tWAERS\n" + "".join("\t".join(r) + "\n" for r in rows)


def spend(client, tokens, content, **kw):
    return client.post("/api/v1/suppliers/import/sap-spend", json={"content": content, **kw},
                       headers=bearer(tokens["access_token"]))


def by_number(apps, org, number):
    suppliers = asyncio.run(apps["coordinator"].store.list_suppliers(org, limit=None))[0]
    return next(s for s in suppliers if s.get("sap_supplier_number") == number)


def test_preview_then_apply_sets_spend_and_rank(client, sarah, apps):
    a, b = numbers(2)
    vendors(client, sarah, [a, b])
    content = orders(["1", a, "15.09.2026", "7.500,00", "EUR"], ["2", b, "15.09.2026", "2.500,00", "EUR"],
                     ["3", "99" + a, "15.09.2026", "1,00", "EUR"])
    preview = spend(client, sarah, content)
    assert preview.status_code == 200, preview.text
    assert preview.json()["applied"] is False and "spend_12m" not in by_number(apps, ORG_1, a)
    assert preview.json()["unknown_count"] == 1
    applied = spend(client, sarah, content, apply=True).json()
    assert applied["written"] >= 2
    sa, sb = by_number(apps, ORG_1, a), by_number(apps, ORG_1, b)
    assert sa["spend_12m"] == {"EUR": "7500.00"} and sb["spend_12m"] == {"EUR": "2500.00"}
    assert sa["spend_rank"] < sb["spend_rank"] and sa["spend_period"]["to"] == "2026-09-15"


def test_read_only_roles_cannot_import(client, auditor):
    assert spend(client, auditor, orders(["1", "1", "2026-09-01", "1.00", "EUR"])).status_code == 403


def test_spend_stays_in_the_callers_org(client, lisa, apps):
    (n,) = numbers(1)
    vendors(client, lisa, [n])
    spend(client, lisa, orders(["1", n, "2026-09-01", "123.00", "JPY"]), apply=True)
    assert by_number(apps, ORG_2, n)["spend_12m"] == {"JPY": "123.00"}
    org1 = asyncio.run(apps["coordinator"].store.list_suppliers(ORG_1, limit=None))[0]
    assert not any(s.get("sap_supplier_number") == n for s in org1)


def test_bad_file_and_ambiguous_amounts(client, sarah):
    assert spend(client, sarah, "Vendor,Value\n1,2\n").status_code == 400
    (n,) = numbers(1)
    vendors(client, sarah, [n])
    body = spend(client, sarah, orders(["1", n, "2026-09-01", "1,234", "EUR"], ["2", n, "2026-09-01", "5.00", "EUR"])).json()
    assert any("read two ways" in w for w in body["warnings"])
    assert spend(client, sarah, orders(["1", n, "2026-09-01", "1,234", "EUR"]), decimal=",").status_code == 200


def test_audit_has_totals_not_amounts(client, sarah):
    (n,) = numbers(1)
    vendors(client, sarah, [n])
    spend(client, sarah, orders(["1", n, "2026-09-01", "424242.00", "EUR"]), apply=True)
    log = client.get("/api/v1/audit?limit=30", headers=bearer(sarah["access_token"])).json()["entries"]
    entry = next(e for e in log if e["action"] == "suppliers.import.sap_spend")
    assert entry["details"]["written"] >= 1 and "424242" not in str(log)
