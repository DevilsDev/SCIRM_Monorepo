"""Purchase-order spend from SAP exports: parsing dates and amounts in SAP's formats,
the 12-month period, currencies kept apart, and the plan for a tenant's suppliers."""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from libs.integrations.sap_spend import parse_amount, parse_date, parse_po_extract, plan_spend, summarize  # noqa: E402

HEADER = ["EBELN", "LIFNR", "BEDAT", "NETWR", "WAERS", "WERKS", "LOEKZ"]


def extract(*rows, header=HEADER, sep="\t"):
    return "\n".join(sep.join(r) for r in [header, *rows]) + "\n"


def line(po, number, when, amount, currency="EUR", plant="DE01", deleted=""):
    return [po, number, when, amount, currency, plant, deleted]


class TestFormats:
    @pytest.mark.parametrize("text,expected", [
        ("15.03.2026", date(2026, 3, 15)),   # DD.MM.YYYY
        ("03/15/2026", date(2026, 3, 15)),   # MM/DD/YYYY
        ("03-15-2026", date(2026, 3, 15)),   # MM-DD-YYYY
        ("2026.03.15", date(2026, 3, 15)),
        ("2026/03/15", date(2026, 3, 15)),
        ("2026-03-15", date(2026, 3, 15)),
        ("20260315", date(2026, 3, 15)),
    ])
    def test_sap_date_formats(self, text, expected):
        assert parse_date(text) == expected

    @pytest.mark.parametrize("text", ["", "15/03/2026", "2026-13-01", "March 2026"])
    def test_unreadable_dates(self, text):
        assert parse_date(text) is None  # 15/03/2026 is not a valid MM/DD/YYYY date

    @pytest.mark.parametrize("text,expected", [
        ("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("1 234,56", "1234.56"),
        ("1.234.567", "1234567"), ("1,234,567.00", "1234567.00"), ("12,50", "12.50"), ("12.5", "12.5"),
        ("123,45-", "-123.45"), ("-99.00", "-99.00"), ("1000", "1000"),
    ])
    def test_amounts(self, text, expected):
        assert parse_amount(text) == Decimal(expected)

    def test_ambiguous_amounts_need_the_decimal_separator(self):
        assert parse_amount("1,234") is None
        assert parse_amount("1,234", decimal=",") == Decimal("1.234")
        assert parse_amount("1,234", decimal=".") == Decimal("1234")


class TestParse:
    def test_reads_and_reports_problems(self):
        lines, warnings = parse_po_extract(extract(
            line("4500000001", "0000100001", "15.03.2026", "1.000,00"),
            line("4500000002", "", "15.03.2026", "5,00"),
            line("4500000003", "100002", "not a date", "5,00"),
            line("4500000004", "100002", "15.03.2026", "1,234"),
            line("4500000005", "100002", "15.03.2026", "5,00", currency=""),
        ))
        assert [(l["number"], l["amount"]) for l in lines] == [("100001", Decimal("1000.00"))]
        assert any("no supplier number" in w for w in warnings)
        assert any("unreadable date" in w for w in warnings)
        assert any("could be read two ways" in w for w in warnings)
        assert any("no currency" in w for w in warnings)

    def test_column_map_for_labelled_exports(self):
        text = extract(["Vendor", "Document Date", "Net Order Value", "Currency"],
                       header=["Vendor", "Document Date", "Net Order Value", "Crcy"])
        assert parse_po_extract(text)[0] == []
        lines, _ = parse_po_extract(extract(["100001", "2026-03-15", "50.00", "USD"],
                                            header=["Vendor", "Document Date", "Net Order Value", "Crcy"]),
                                    column_map={"number": "Vendor", "date": "Document Date",
                                                "amount": "Net Order Value", "currency": "Crcy"})
        assert lines[0]["currency"] == "USD" and lines[0]["amount"] == Decimal("50.00")


class TestSummary:
    def test_period_deletions_and_currencies(self):
        lines, _ = parse_po_extract(extract(
            line("45001", "1", "2026-09-30", "1000.00"),
            line("45001", "1", "2026-09-30", "500.00"),             # second item, same order
            line("45002", "1", "2025-10-01", "200.00"),             # first day of the period
            line("45003", "1", "2025-09-30", "999.00"),             # before the period
            line("45004", "2", "2026-06-01", "300.00", deleted="L"),  # deleted item
            line("45005", "2", "2026-06-01", "400.00", currency="USD"),
            line("45006", "3", "2026-01-01", "100.00-"),             # credit
        ))
        s = summarize(lines)
        assert s["period"] == {"from": "2025-10-01", "to": "2026-09-30"}
        assert s["suppliers"]["1"]["spend"] == {"EUR": "1700.00"} and s["suppliers"]["1"]["orders"] == 2
        assert s["suppliers"]["2"]["spend"] == {"USD": "400.00"}  # never added to EUR
        assert s["suppliers"]["3"]["spend"] == {"EUR": "-100.00"}
        assert s["main_currency"] == "EUR" and s["currencies"] == {"EUR": "1600.00", "USD": "400.00"}
        assert s["lines"] == {"read": 7, "deleted": 1, "before_period": 1, "counted": 5}


class TestPlan:
    def test_ranks_replaces_and_reports_unknown_numbers(self):
        lines, _ = parse_po_extract(extract(
            line("1", "100", "2026-09-01", "900.00"), line("2", "200", "2026-09-01", "100.00"),
            line("3", "999", "2026-09-01", "5000.00"),
        ))
        existing = [{"id": "a", "name": "A", "sap_supplier_number": "100"},
                    {"id": "b", "name": "B", "sap_supplier_number": "200"},
                    {"id": "c", "name": "C (no orders)", "sap_supplier_number": "300", "spend_12m": {"EUR": "1"}},
                    {"id": "m", "name": "Manual, not from SAP"}]
        plan = plan_spend(summarize(lines), existing)
        fields = {u["supplier_id"]: u["fields"] for u in plan["updates"]}
        assert set(fields) == {"a", "b", "c"}  # manual suppliers are not touched
        assert fields["a"]["spend_rank"] == 1 and fields["a"]["spend_share"] == 0.15  # 900 of 6,000
        assert fields["c"]["spend_12m"] == {} and fields["c"]["spend_orders"] == 0  # replaced, not kept
        assert plan["unknown_suppliers"] == [{"number": "999", "spend": {"EUR": "5000.00"}}]
        assert [t["number"] for t in plan["top"]] == ["100", "200", "300"]

    def test_an_empty_period_gives_no_ranking(self):
        plan = plan_spend(summarize([]), [{"id": "a", "sap_supplier_number": "1"}])
        assert plan["updates"][0]["fields"]["spend_rank"] is None
