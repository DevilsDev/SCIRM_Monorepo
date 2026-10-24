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
from intel_support import fixture, fixture_text, recorded_transport  # noqa: E402


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


class TestWarningLetters:
    @pytest.fixture(scope="class")
    def rows(self):
        return fixture("warning_letters.json")["data"]

    @pytest.fixture(scope="class")
    def signals(self, rows):
        return [s for s in map(sources.parse_warning_letter, rows) if s]

    def test_tobacco_letters_are_left_out(self, rows, signals):
        tobacco = [r for r in rows if "Tobacco" in r[3]]
        assert tobacco and len(signals) == len(rows) - len(tobacco)
        assert not any("Tobacco" in s["raw"]["office"] for s in signals)

    def test_published_is_the_posting_date_not_the_letter_date(self, signals):
        for s in signals:
            assert s["published_at"] == s["raw"]["posted_date"]
            assert s["occurred_at"] <= s["published_at"]
        assert any(s["occurred_at"] < s["published_at"] for s in signals)

    def test_severity_and_product_area(self, signals):
        for s in signals:
            assert s["severity"] == ("high" if "cgmp" in s["raw"]["subject"].lower() else "medium")
        areas = {s["raw"]["product_area"] for s in signals}
        assert {"drugs", "food"} <= areas

    def test_company_url_and_keys(self, signals):
        s = signals[0]
        assert s["url"].startswith("https://www.fda.gov/") and s["entity_names"] and s["entity_keys"]
        assert s["signal_type"] == "warning_letter"

    @pytest.mark.parametrize("office, subject, area", [
        ("Center for Drug Evaluation and Research (CDER)", "CGMP/Finished Pharmaceuticals/Adulterated", "drugs"),
        ("Division of Pharmaceutical Quality Operations IV", "CGMP/Active Pharmaceutical Ingredient", "drugs"),
        ("Center for Biologics Evaluation and Research (CBER)", "Deviations", "biologics"),
        ("Center for Devices and Radiological Health", "CGMP/QSR/Medical Devices", "devices"),
        ("Human Foods Program", "CGMP/Food/Adulterated", "food"),
        ("Division of West Coast Imports", "Foreign Supplier Verification Program (FSVP)", "food"),
        ("Office of Inspections and Investigations", "CGMP/Finished Pharmaceuticals/Adulterated", "drugs"),
        ("Center for Veterinary Medicine", "New Animal Drug", "veterinary"),
    ])
    def test_product_area(self, office, subject, area):
        assert sources.product_area(office, subject) == area


class TestImportAlerts:
    def test_index_rows(self):
        rows = sources.parse_import_alert_index(fixture_text("import_alert_list.html"))
        assert [r["number"] for r in rows] == ["16-02", "66-40", "89-08"]
        assert rows[1]["page"] == "importalert_189.html" and "GMP" in rows[1]["title"]

    def test_red_list_firms_with_their_own_dates_and_countries(self):
        signals = sources.parse_import_alert(fixture_text("import_alert_66_40.html"), "66-40",
                                             "Drugs From Firms Which Have Not Met Drug GMPs", "https://x")
        firms = {s["entity_names"][0]: s for s in signals}
        assert "Aruba Aloe Balm N.V." in firms
        aruba = firms["Aruba Aloe Balm N.V."]
        assert aruba["country_codes"] == ["AW"] and aruba["published_at"] == "2024-04-15"
        assert all(s["severity"] == "high" and s["signal_type"] == "import_alert" for s in signals)

    def test_green_list_firms_are_not_listed(self):
        page = (fixture_text("import_alert_66_40.html").replace("</body></html>", "") +
                '<a name="GreenFirm"></a><div class="center"><h4>INDIA</h4></div>'
                '<div class="div-info"><div class="div-name floatleft">Exempt Good Standing Ltd</div>'
                '<div class="div-name floatright">Date Published : 01/02/2026</div><div class="clear">Mumbai</div>'
                '</div></body></html>')
        names = {s["entity_names"][0] for s in sources.parse_import_alert(page, "66-40", "GMP", "u")}
        assert "Exempt Good Standing Ltd" not in names and "Aruba Aloe Balm N.V." in names

    def test_non_gmp_alerts_are_medium(self):
        [one] = sources.parse_import_alert(fixture_text("import_alert_66_40.html"), "66-41",
                                           "Unapproved New Drugs Promoted In The U.S.", "u")[-1:]
        assert one["severity"] == "medium"

    def test_only_drug_device_and_biologic_alerts_are_fetched(self):
        async def go():
            async with httpx.AsyncClient(transport=recorded_transport()) as client:
                return await sources.fetch_import_alerts(client, date(2020, 1, 1), date(2026, 10, 20))
        result = asyncio.run(go())
        assert {s["raw"]["alert"] for s in result.signals} == {"66-40"}  # 16-02 (food) skipped; 89-08 page empty


class TestCollect:
    def run(self, transport):
        async def go():
            async with httpx.AsyncClient(transport=transport) as client:
                return await sources.collect(client, 90, today=date(2026, 10, 20))
        return {r.source: r for r in asyncio.run(go())}

    def test_all_sources_ok_on_recorded_data(self):
        results = self.run(recorded_transport())
        assert set(results) == set(sources.SOURCES)
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


class TestEma:
    """EMA's JSON data files (recorded): shortages, DHPCs and referrals, human medicines only."""

    def run(self, only):
        async def go():
            async with httpx.AsyncClient(transport=recorded_transport()) as client:
                return await sources.collect(client, 36500, today=date(2026, 10, 24), only=only)
        return {r.source: r for r in asyncio.run(go())}

    def test_shortages_are_a_snapshot_with_status_and_substances(self):
        result = self.run(["ema_shortages"])["ema_shortages"]
        assert result.status == "ok" and "ema_shortages" in sources.SNAPSHOT_SOURCES
        by_id = {s["external_id"]: s for s in result.signals}
        ongoing = by_id["human-normal-immunoglobulins"]
        assert ongoing["signal_type"] == "ema_shortage" and ongoing["severity"] == "medium"
        assert ongoing["published_at"] == "2024-06-03" and ongoing["updated_at"] == "2026-09-22"
        assert ongoing["raw"]["substances"] == ["human normal immunoglobulins"] and ongoing["entity_names"] == []
        assert by_id["dynastat"]["severity"] == "low" and by_id["dynastat"]["raw"]["status"] == "resolved"
        assert by_id["natpar"]["raw"]["status"] == "discontinued"

    def test_an_ongoing_shortage_without_alternatives_is_high(self):
        row = {**fixture("ema_shortages.json")["data"][0], "availability_of_alternatives": "No"}
        assert sources.parse_ema_shortage(row)["severity"] == "high"

    def test_dhpcs_and_referrals_skip_veterinary_medicines(self):
        results = self.run(["ema_dhpc", "ema_referrals"])
        dhpc, referrals = results["ema_dhpc"].signals, results["ema_referrals"].signals
        assert len(dhpc) == 3 and len(referrals) == 3  # each fixture has one veterinary row
        jentadueto = next(s for s in dhpc if "Jentadueto" in s["title"])
        assert jentadueto["raw"]["substances"] == ["linagliptin", "metformin hydrochloride"]
        assert jentadueto["signal_type"] == "safety_communication" and jentadueto["published_at"] == "2026-08-20"
        rifadin = next(s for s in referrals if "Rifadin" in s["title"])
        assert rifadin["severity"] == "medium" and rifadin["raw"]["substances"] == ["rifampicin"]
        assert all(s["severity"] == "low" for s in referrals if s["raw"]["final"])

    def test_the_lookback_applies_to_history_not_to_the_shortage_list(self):
        async def go():
            async with httpx.AsyncClient(transport=recorded_transport()) as client:
                return await sources.collect(client, 30, today=date(2026, 10, 24),
                                             only=["ema_shortages", "ema_dhpc", "ema_referrals"])
        results = {r.source: r for r in asyncio.run(go())}
        assert len(results["ema_shortages"].signals) == 3
        assert [s["external_id"] for s in results["ema_referrals"].signals] == ["EMA/REF/0000355053"]
        assert results["ema_dhpc"].signals == []  # the newest recorded DHPC is from August

    def test_a_changed_file_format_is_an_error_not_an_empty_list(self):
        def handler(request):
            return httpx.Response(200, json={"unexpected": True})

        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await sources.collect(client, 30, only=["ema_shortages"])
        [result] = asyncio.run(go())
        assert result.status == "error" and result.signals == []
