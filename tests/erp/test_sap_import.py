"""SAP supplier master import: parsing LFA1 extracts and planning what an import changes.
The extracts here are synthetic, in the column layout of table LFA1."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from libs.integrations.sap_import import normalize_number, parse_extract, plan_import  # noqa: E402

HEADER = ["LIFNR", "NAME1", "NAME2", "LAND1", "ORT01", "SPERR", "SPERM", "LOEVM", "STCEG"]


def extract(*rows, sep="\t", header=HEADER):
    return "\n".join(sep.join(r) for r in [header, *rows]) + "\n"


def row(number, name, name2="", country="DE", blocked="", deleted=""):
    return [number, name, name2, country, "Berlin", blocked, "", deleted, ""]


def parse(text, **kw):
    rows, warnings = parse_extract(text, **kw)
    return rows, warnings


def stored(plan, existing=None):
    """Apply a plan to a list of supplier dicts, as the coordinator does with the store."""
    existing = [dict(s) for s in (existing or [])]
    by_id = {s["id"]: s for s in existing}
    for i, a in enumerate(plan["actions"]):
        if a["action"] == "create":
            s = {"id": f"new-{a['number']}-{i}", **a["fields"]}
            existing.append(s)
            by_id[s["id"]] = s
        elif a["action"] in ("update", "link", "deactivate"):
            by_id[a["supplier_id"]].update(a["fields"])
    return existing


def actions(plan, kind):
    return [a for a in plan["actions"] if a["action"] == kind]


class TestParse:
    def test_supplier_numbers_lose_leading_zeros(self):
        assert normalize_number("0000100123") == normalize_number("100123") == "100123"
        assert normalize_number("  ab-7 ") == "AB-7"
        assert normalize_number("0000") == "0"

    def test_tab_semicolon_and_bom(self):
        for text in (extract(row("0000100001", "Acme Pharma GmbH")),
                     "﻿" + extract(row("100001", "Acme Pharma GmbH"), sep=";")):
            rows, warnings = parse(text)
            assert [(r["number"], r["name"], r["country_code"]) for r in rows] == [("100001", "Acme Pharma GmbH", "DE")]
            assert warnings == []

    def test_a_full_name1_continues_in_name2(self):
        long_name = "Very Long Pharmaceutical Ingredient"  # 35 characters, the length of NAME1
        assert len(long_name) == 35
        rows, _ = parse(extract(row("1", long_name, "Manufacturers Ltd")))
        assert rows[0]["name"] == f"{long_name} Manufacturers Ltd" and rows[0]["aliases"] == []

    def test_name2_is_an_alias_only_when_it_reads_as_a_company(self):
        rows, _ = parse(extract(row("1", "Acme Pharma", "Acme Holdings AG"), row("2", "Beta Labs", "c/o Purchasing GmbH"),
                                row("3", "Gamma Chem", "Quality department"), row("4", "Delta", "2nd floor Ltd")))
        assert [r["aliases"] for r in rows] == [["Acme Holdings AG"], [], [], []]

    def test_flags_and_bad_rows(self):
        rows, warnings = parse(extract(row("1", "Blocked Co", blocked="X"), row("2", "Gone Co", deleted="X"),
                                       row("", "No Number Co"), row("01", "Duplicate of 1"), row("5", "Nowhere Co", country="ZZZ")))
        assert [(r["number"], r["blocked"], r["deletion_flag"]) for r in rows] == \
            [("1", True, False), ("2", False, True), ("5", False, False)]
        assert rows[2]["country_code"] is None
        assert any("Row 4" in w for w in warnings) and any("Row 5" in w and "already appears" in w for w in warnings)
        assert any("ZZZ" in w for w in warnings)

    def test_required_columns_and_column_map(self):
        labels = ["Supplier", "Name 1", "Country"]
        text = extract(["100", "Acme Pharma GmbH", "FR"], header=labels)
        rows, warnings = parse(text)
        assert rows == [] and "LIFNR" in warnings[0] and "Supplier" in warnings[0]
        rows, warnings = parse(text, column_map={"number": "Supplier", "name1": "Name 1", "country": "Country"})
        assert [(r["number"], r["country_code"]) for r in rows] == [("100", "FR")]

    def test_empty_file(self):
        assert parse("") == ([], ["The file is empty."])


class TestPlan:
    def test_first_import_creates_with_sap_codes(self):
        rows, _ = parse(extract(row("0000100001", "Acme Pharma GmbH", "Acme Holdings AG"), row("2", "Blocked Co", blocked="X")))
        plan = plan_import(rows, [])
        assert plan["summary"] == {"create": 2}
        created = {a["number"]: a["fields"] for a in actions(plan, "create")}
        assert created["100001"]["supplier_code"] == "SAP-100001"
        assert created["100001"]["aliases"] == ["Acme Holdings AG"] and created["100001"]["is_active"] is True
        assert created["2"]["is_active"] is False  # blocked in SAP

    def test_reimport_with_padded_numbers_is_unchanged(self):
        first = stored(plan_import(parse(extract(row("100001", "Acme Pharma GmbH")))[0], []))
        again = plan_import(parse(extract(row("0000100001", "Acme Pharma GmbH")))[0], first)
        assert again["summary"] == {"unchanged": 1}

    def test_changes_are_updates_and_manual_aliases_survive(self):
        suppliers = stored(plan_import(parse(extract(row("1", "Acme Pharma GmbH", "Acme Holdings AG")))[0], []))
        suppliers[0]["aliases"] = suppliers[0]["aliases"] + ["Acme Europe"]  # added by hand in SCIRM
        plan = plan_import(parse(extract(row("1", "Acme Pharma GmbH", country="FR")))[0], suppliers)
        assert plan["summary"] == {"update": 1}
        assert actions(plan, "update")[0]["changed"] == ["country_code"]
        assert "aliases" not in actions(plan, "update")[0]["fields"]  # nothing removed
        assert stored(plan, suppliers)[0]["aliases"] == ["Acme Holdings AG", "Acme Europe"]

    def test_a_manual_deactivation_is_not_undone(self):
        suppliers = stored(plan_import(parse(extract(row("1", "Acme Pharma GmbH")))[0], []))
        suppliers[0]["is_active"] = False
        plan = plan_import(parse(extract(row("1", "Acme Pharma GmbH")))[0], suppliers)
        assert plan["summary"] == {"unchanged": 1}
        blocked = plan_import(parse(extract(row("1", "Acme Pharma GmbH", blocked="X")))[0], suppliers)
        assert actions(blocked, "update")[0]["fields"]["sap_blocked"] is True

    def test_unblocking_in_sap_reactivates(self):
        suppliers = stored(plan_import(parse(extract(row("1", "Acme Pharma GmbH", blocked="X")))[0], []))
        plan = plan_import(parse(extract(row("1", "Acme Pharma GmbH")))[0], suppliers)
        assert stored(plan, suppliers)[0]["is_active"] is True

    def test_deletion_flag(self):
        suppliers = stored(plan_import(parse(extract(row("1", "Acme Pharma GmbH")))[0], []))
        plan = plan_import(parse(extract(row("1", "Acme Pharma GmbH", deleted="X"), row("2", "Never Imported", deleted="X")))[0],
                           suppliers)
        assert plan["summary"] == {"deactivate": 1, "skip": 1}

    def test_a_name_clash_with_a_manual_supplier_waits_for_a_decision(self):
        manual = [{"id": "m1", "supplier_code": "SUP-ACME", "name": "ACME Pharma GmbH", "aliases": ["Acme"]}]
        rows, _ = parse(extract(row("1", "Acme Pharma GmbH")))
        plan = plan_import(rows, manual)
        assert plan["summary"] == {"needs_decision": 1}
        assert plan["duplicates"][0]["existing_id"] == "m1"
        linked = plan_import(rows, manual, {"1": "link:m1"})
        assert linked["summary"] == {"link": 1}
        after = stored(linked, manual)
        assert after[0]["supplier_code"] == "SUP-ACME" and after[0]["sap_supplier_number"] == "1"
        assert after[0]["aliases"] == ["Acme"]
        assert plan_import(rows, after)["summary"] == {"unchanged": 1}  # recognised by number from now on
        assert plan_import(rows, manual, {"1": "create"})["summary"] == {"create": 1}

    def test_a_link_must_be_to_an_available_supplier(self):
        manual = [{"id": "m1", "supplier_code": "SUP-ACME", "name": "Acme Pharma GmbH"}]
        rows, _ = parse(extract(row("1", "Acme Pharma GmbH"), row("2", "Other Co")))
        plan = plan_import(rows, manual, {"1": "link:not-in-this-org", "2": "link:m1"})
        assert [a["action"] for a in plan["actions"]] == ["skip", "link"]
        twice = plan_import(parse(extract(row("1", "A Co"), row("2", "B Co")))[0], manual, {"1": "link:m1", "2": "link:m1"})
        assert [a["action"] for a in twice["actions"]] == ["link", "skip"]

    def test_missing_suppliers_are_reported_and_deactivated_only_on_request(self):
        suppliers = stored(plan_import(parse(extract(*(row(str(n), f"Firm {n} GmbH") for n in range(1, 5))))[0], []))
        three = parse(extract(*(row(str(n), f"Firm {n} GmbH") for n in range(1, 4))))[0]
        plan = plan_import(three, suppliers)
        assert [m["number"] for m in plan["missing"]] == ["4"] and "deactivate" not in plan["summary"]
        plan = plan_import(three, suppliers, deactivate_missing=True)
        assert plan["missing_deactivated"] and plan["summary"]["deactivate"] == 1
        after = stored(plan, suppliers)
        back = plan_import(parse(extract(*(row(str(n), f"Firm {n} GmbH") for n in range(1, 5))))[0], after)
        assert stored(back, after)[3]["is_active"] is True  # it came back in SAP

    def test_a_much_smaller_file_does_not_deactivate(self):
        suppliers = stored(plan_import(parse(extract(*(row(str(n), f"Firm {n} GmbH") for n in range(1, 11))))[0], []))
        plan = plan_import(parse(extract(row("1", "Firm 1 GmbH")))[0], suppliers, deactivate_missing=True)
        assert plan["guard"] and not plan["missing_deactivated"] and "deactivate" not in plan["summary"]

    def test_a_code_already_used_by_hand_waits_for_a_decision(self):
        manual = [{"id": "m1", "supplier_code": "SAP-100", "name": "Something Else Entirely"}]
        rows, _ = parse(extract(row("0000000100", "Acme Pharma GmbH")))
        plan = plan_import(rows, manual)
        assert plan["summary"] == {"needs_decision": 1} and plan["duplicates"][0]["existing_id"] == "m1"
        assert plan_import(rows, manual, {"100": "create"})["summary"] == {"skip": 1}  # the code is taken
        assert plan_import(rows, manual, {"100": "link:m1"})["summary"] == {"link": 1}

    def test_a_code_used_by_another_sap_number_is_skipped(self):
        other = [{"id": "s1", "supplier_code": "SAP-100", "name": "Old", "sap_supplier_number": "ABC"}]
        plan = plan_import(parse(extract(row("100", "Acme Pharma GmbH")))[0], other)
        assert plan["summary"] == {"skip": 1} and "SAP-100" in plan["actions"][0]["reason"]

    def test_linking_does_not_reactivate_a_manual_deactivation(self):
        manual = [{"id": "m1", "supplier_code": "SUP-ACME", "name": "Acme Pharma GmbH", "is_active": False}]
        rows, _ = parse(extract(row("1", "Acme Pharma GmbH")))
        assert stored(plan_import(rows, manual, {"1": "link:m1"}), manual)[0]["is_active"] is False
        blocked, _ = parse(extract(row("1", "Acme Pharma GmbH", blocked="X")))
        active = [{**manual[0], "is_active": True}]
        assert stored(plan_import(blocked, active, {"1": "link:m1"}), active)[0]["is_active"] is False

    def test_a_renamed_or_linked_supplier_keeps_its_old_name_as_an_alias(self):
        manual = [{"id": "m1", "supplier_code": "SUP-G", "name": "Glenmark Generics Inc"}]
        rows, _ = parse(extract(row("1", "Glenmark Pharmaceuticals Inc.")))
        after = stored(plan_import(rows, manual, {"1": "link:m1"}), manual)
        assert after[0]["name"] == "Glenmark Pharmaceuticals Inc."
        assert after[0]["aliases"] == ["Glenmark Generics Inc"]
        # Only a real change of name adds one: punctuation or a country suffix is the same name.
        same = plan_import(parse(extract(row("1", "Glenmark Pharmaceuticals Inc., USA")))[0], after)
        assert "aliases" not in actions(same, "update")[0]["fields"]
