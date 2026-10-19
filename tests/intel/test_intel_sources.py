"""Source connectors, parsed from recorded (trimmed) real payloads; no network."""

import asyncio
import sys
from datetime import date
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from libs.intel import sources  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from intel_support import fixture, recorded_transport  # noqa: E402


class TestRecalls:
    @pytest.fixture(scope="class")
    def signals(self):
        return [s for s in map(sources.parse_recall, fixture("fda_enforcement.json")["results"]) if s]

    def test_every_record_parses(self, signals):
        assert len(signals) == len(fixture("fda_enforcement.json")["results"])

    def test_published_is_the_report_date_not_the_earlier_initiation_date(self, signals):
        """Point-in-time correctness: a recall is knowable from its FDA report date."""
        for s in signals:
            raw = s["raw"]
            assert s["published_at"] == f"{raw['report_date'][:4]}-{raw['report_date'][4:6]}-{raw['report_date'][6:]}"
            assert s["occurred_at"] <= s["published_at"]
        assert any(s["occurred_at"] < s["published_at"] for s in signals)

    def test_severity_follows_fda_classification(self, signals):
        expected = {"Class I": "critical", "Class II": "high", "Class III": "medium"}
        for s in signals:
            assert s["severity"] == expected.get(s["raw"]["classification"], "medium")
        assert {"critical", "high", "medium"} <= {s["severity"] for s in signals}

    def test_company_names_and_countries_are_kept(self, signals):
        glenmark = next(s for s in signals if s["raw"]["recalling_firm"].startswith("Glenmark"))
        assert "Glenmark Pharmaceuticals Inc., USA" in glenmark["entity_names"]
        assert glenmark["entity_keys"] == ["glenmark"]
        india = [s for s in signals if s["raw"]["country"] == "India"]
        assert india and all(s["country_codes"] == ["IN"] for s in india)


class TestShortages:
    @pytest.fixture(scope="class")
    def signals(self):
        return sources.parse_shortages(fixture("fda_shortages.json")["results"])

    def test_one_signal_per_company_and_drug(self, signals):
        lidocaine = [s for s in signals if s["raw"]["company_name"].startswith("Hospira")
                     and s["raw"]["generic_name"].startswith("Lidocaine")]
        assert len(lidocaine) == 1 and lidocaine[0]["raw"]["presentations"] > 1

    def test_listed_but_available_is_low_not_high(self, signals):
        lidocaine = next(s for s in signals if s["raw"]["generic_name"].startswith("Lidocaine")
                         and s["raw"]["company_name"].startswith("Hospira"))
        assert set(lidocaine["raw"]["availability"]) == {"Available"}
        assert lidocaine["severity"] == "low"

    def test_unavailable_is_high_and_limited_is_medium(self, signals):
        by_availability = {tuple(sorted(s["raw"]["availability"])): s["severity"] for s in signals
                           if s["signal_type"] == "shortage"}
        assert by_availability[("Unavailable",)] == "high"
        assert by_availability[("Limited Availability",)] == "medium"

    def test_partly_unavailable_is_medium(self):
        records = [{"company_name": "X Co", "generic_name": "Drug", "status": "Current",
                    "availability": a, "initial_posting_date": "01/02/2025", "update_date": "03/04/2026"}
                   for a in ("Available", "Available", "Available", "Unavailable")]
        [signal] = sources.parse_shortages(records)
        assert signal["severity"] == "medium"
        assert signal["published_at"] == "2025-01-02" and signal["updated_at"] == "2026-03-04"

    def test_discontinuations_are_their_own_type_and_resolved_is_dropped(self, signals):
        assert {s["signal_type"] for s in signals} == {"shortage", "discontinuation"}
        assert not any(s["raw"]["status"] == "Resolved" for s in signals)

    def test_parent_company_is_a_lookup_key(self, signals):
        hospira = next(s for s in signals if s["raw"]["company_name"].startswith("Hospira"))
        assert set(hospira["entity_keys"]) == {"hospira", "pfizer"}


class TestGdacs:
    @pytest.fixture(scope="class")
    def signals(self):
        return [s for s in map(sources.parse_gdacs, fixture("gdacs.json")["features"]) if s]

    def test_only_orange_and_red_alerts(self, signals):
        levels = [f["properties"]["alertlevel"] for f in fixture("gdacs.json")["features"]]
        assert "Green" in levels
        assert len(signals) == sum(level in ("Orange", "Red") for level in levels)
        assert {s["severity"] for s in signals} == {"critical", "high"}

    def test_countries_come_from_affected_countries(self, signals):
        assert all(s["country_codes"] and all(len(c) == 2 for c in s["country_codes"]) for s in signals)
        assert all(s["signal_type"] == "disaster" and s["entity_names"] == [] for s in signals)


class TestCollect:
    def run(self, transport):
        async def go():
            async with httpx.AsyncClient(transport=transport) as client:
                return await sources.collect(client, 90, today=date(2026, 10, 20))
        return {r.source: r for r in asyncio.run(go())}

    def test_all_sources_ok_on_recorded_data(self):
        results = self.run(recorded_transport())
        assert set(results) == {"fda_recalls", "fda_shortages", "gdacs"}
        assert all(r.status == "ok" and r.signals for r in results.values())

    def test_a_failing_source_is_reported_and_others_still_run(self):
        results = self.run(recorded_transport({"www.gdacs.org": 500}))
        assert results["gdacs"].status == "error" and results["gdacs"].signals == []
        assert results["gdacs"].error == "HTTP 500"
        assert results["fda_recalls"].status == "ok" and results["fda_recalls"].signals

    def test_rate_limiting_is_distinguished(self):
        results = self.run(recorded_transport({"api.fda.gov": 429}))
        assert results["fda_recalls"].status == "rate_limited"
        assert results["fda_shortages"].status == "rate_limited"

    def test_no_matches_is_not_an_error(self):
        results = self.run(recorded_transport({"api.fda.gov": 404}))
        assert results["fda_recalls"].status == "ok" and results["fda_recalls"].signals == []
