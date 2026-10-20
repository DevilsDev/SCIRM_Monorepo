"""Supplier scan: CSV parsing, matching rules in the report, and report safety."""

import asyncio
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from intel_support import fixture, fixture_text  # noqa: E402
from libs.common.store import MemoryStore  # noqa: E402
from libs.intel import scan, sources  # noqa: E402


class TestParse:
    def test_semicolons_bom_country_names_and_aliases(self):
        text = "﻿Supplier Name;Country;Aliases\nSun Pharmaceutical Industries, Inc.;India;Sun Pharma|SPIL\nB. Braun Medical Inc.;us;\n"
        suppliers, warnings = scan.parse_supplier_csv(text)
        assert warnings == []
        assert suppliers[0] == {"id": "row-2", "name": "Sun Pharmaceutical Industries, Inc.", "country_code": "IN",
                                "aliases": ["Sun Pharma", "SPIL"]}
        assert suppliers[1]["country_code"] == "US"

    def test_commas_and_alternative_headers(self):
        suppliers, _ = scan.parse_supplier_csv("company,location\n\"Acme, Inc.\",Germany\n")
        assert suppliers == [{"id": "row-2", "name": "Acme, Inc.", "country_code": "DE", "aliases": []}]

    def test_problems_are_reported_not_hidden(self):
        text = "name,country\nAcme Inc,Narnia\n,US\nACME INC.,US\n\n"
        suppliers, warnings = scan.parse_supplier_csv(text)
        assert [s["name"] for s in suppliers] == ["Acme Inc"]
        assert any("Narnia" in w for w in warnings)
        assert any("no name" in w for w in warnings)
        assert any("more than once" in w for w in warnings)

    def test_a_missing_name_column_explains_itself(self):
        suppliers, warnings = scan.parse_supplier_csv("vat number,city\n123,Berlin\n")
        assert suppliers == [] and "name column" in warnings[0]

    def test_row_limit(self):
        text = "name\n" + "\n".join(f"Firm Number {i} GmbH" for i in range(scan.MAX_SUPPLIERS + 5))
        suppliers, warnings = scan.parse_supplier_csv(text)
        assert len(suppliers) == scan.MAX_SUPPLIERS and any("first 500" in w for w in warnings)


@pytest.fixture(scope="module")
def store():
    signals = [s for s in map(sources.parse_recall, fixture("fda_enforcement.json")["results"]) if s]
    signals += sources.parse_shortages(fixture("fda_shortages.json")["results"])
    signals += sources.parse_import_alert(fixture_text("import_alert_66_40.html"), "66-40", "Drug GMPs", "https://x")
    signals += [s for s in map(sources.parse_gdacs, fixture("gdacs.json")["features"]) if s]
    st = MemoryStore(seed_demo=False)
    asyncio.run(st.upsert_signals(signals))
    return st


def run(store, suppliers, as_of=date(2026, 10, 20)):
    return asyncio.run(scan.run_scan(store, suppliers, as_of=as_of, coverage="test fixtures"))


class TestScan:
    def test_records_are_grouped_cited_and_counted(self, store):
        report = run(store, [{"name": "Glenmark Pharmaceuticals Inc., USA", "country_code": "IN", "aliases": []}])
        glenmark = report["suppliers"][0]
        assert glenmark["counts"].get("recall") == 2 and glenmark["recall_events"] >= 1
        assert all(r["url"] and r["published_at"] for r in glenmark["records"])
        assert report["summary"] == {**report["summary"], "scanned": 1, "with_records": 1}

    def test_parent_company_matches_are_marked_for_checking(self, store):
        pfizer = run(store, [{"name": "Pfizer Inc.", "aliases": []}])["suppliers"][0]
        assert any(r["check"] and r["match"] == "parent_company" for r in pfizer["records"])

    def test_country_alone_is_exposure_not_a_record(self, store):
        report = run(store, [{"name": "Unrelated Widgets GmbH", "country_code": "JP", "aliases": []}],
                     as_of=date(2026, 10, 20))
        widgets = report["suppliers"][0]
        assert widgets["records"] == [] and widgets["exposures"] and widgets["watch"] is False

    def test_watch_suppliers_come_first(self, store):
        report = run(store, [{"name": "Unrelated Widgets GmbH", "aliases": []},
                             {"name": "Glenmark Pharmaceuticals Inc., USA", "aliases": []}], as_of=date(2025, 6, 1))
        names = [s["name"] for s in report["suppliers"]]
        assert names[0] == "Glenmark Pharmaceuticals Inc., USA"


class TestReport:
    def test_untrusted_names_are_escaped_and_no_script_runs(self, store):
        evil = '<script>alert(1)</script> "Acme" & Co'
        report = run(store, [{"name": evil, "aliases": ['<img src=x onerror=alert(1)>']}])
        page = scan.render_html(report, prepared_for='<b>Prospect</b>')
        # No live tags from the input: the text survives only in escaped form.
        assert "<script" not in page.lower() and "<img" not in page.lower()
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "&lt;b&gt;Prospect&lt;/b&gt;" in page

    def test_only_web_links_are_linked(self, store):
        report = run(store, [{"name": "Glenmark Pharmaceuticals Inc., USA", "aliases": []}])
        report["suppliers"][0]["records"][0]["url"] = "javascript:alert(1)"
        page = scan.render_html(report)
        assert 'href="javascript' not in page
        assert all(h.startswith(("https://", "http://")) for h in re.findall(r'href="([^"]+)"', page))

    def test_no_records_says_what_was_searched_without_claiming_safety(self, store):
        page = scan.render_html(run(store, [{"name": "Nowhere Pharma Ltd", "aliases": []}]))
        assert "not proof that nothing happened" in page and "test fixtures" in page

    def test_watch_is_explained_with_its_limits(self, store):
        page = scan.render_html(run(store, [{"name": "Glenmark Pharmaceuticals Inc., USA", "aliases": []}]))
        assert "not a prediction" in page
