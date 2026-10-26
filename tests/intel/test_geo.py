"""Supplier sites and site-level disaster exposure (libs/intel/geo.py and matching)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from libs.intel import geo, matching, sources  # noqa: E402

KOBE = {"id": "s1", "label": "Plant", "city": "Kobe", "country": "JP", "lat": 34.69, "lon": 135.19, "precision": "city"}


def quake(lat, lon, alert="Orange", countries=("JP",), eventtype="EQ"):
    return {"id": f"q-{lat}-{lon}", "signal_type": "disaster", "country_codes": list(countries), "entity_names": [],
            "raw": {"eventtype": eventtype, "alertlevel": alert, "lat": lat, "lon": lon}}


class TestGazetteer:
    @pytest.mark.parametrize("city", ["Köln", "Koln", "koeln", "Cologne", "  COLOGNE "])
    def test_names_and_alternates(self, city):
        found = geo.locate(city, "de")
        assert found and abs(found["lat"] - 50.93) < 0.1 and found["precision"] == "city"

    def test_ambiguous_names_are_marked(self):
        found = geo.locate("Springfield", "US")
        assert found["precision"] == "city_ambiguous" and found["candidates"] > 1

    def test_unknown_or_missing(self):
        assert geo.locate("Nowhereville", "DE") is None
        assert geo.locate("Berlin", "FR") is None  # wrong country
        assert geo.locate(None, "DE") is None and geo.locate("Berlin", None) is None

    def test_distance(self):
        berlin, munich = geo.locate("Berlin", "DE"), geo.locate("Munich", "DE")
        assert 480 < geo.distance_km(berlin["lat"], berlin["lon"], munich["lat"], munich["lon"]) < 520


class TestExposure:
    def test_a_site_within_the_radius_is_exposed(self):
        m = matching.match_supplier({"name": "Acme", "sites": [KOBE]}, quake(34.6, 135.0))  # ~20 km
        assert m["match_type"] == "site_proximity" and m["kind"] == "exposure"
        assert m["site"]["distance_km"] < 30 and m["site"]["radius_km"] == 150

    def test_an_alert_elsewhere_in_the_country_is_not(self):
        assert matching.match_supplier({"name": "Acme", "sites": [KOBE]}, quake(35.68, 139.69)) is None  # Tokyo, ~400 km

    def test_radius_depends_on_event_type_and_alert(self):
        supplier = {"name": "Acme", "sites": [KOBE]}
        tokyo = (35.68, 139.69)  # ~410 km from Kobe
        assert matching.match_supplier(supplier, quake(*tokyo, alert="Red")) is None  # earthquake: 300 km
        assert matching.match_supplier(supplier, quake(*tokyo, alert="Orange", eventtype="TC")) is None  # 300 km
        assert matching.match_supplier(supplier, quake(*tokyo, alert="Red", eventtype="TC"))["site"]["radius_km"] == 500

    def test_without_a_usable_point_it_falls_back_to_the_country(self):
        drought = quake(None, None, eventtype="DR")
        m = matching.match_supplier({"name": "Acme", "sites": [KOBE]}, drought)
        assert m["match_type"] == "country_exposure" and m["matched_on"] == "JP"

    def test_suppliers_without_located_sites_keep_country_exposure(self):
        m = matching.match_supplier({"name": "Acme", "country_code": "JP"}, quake(35.68, 139.69))
        assert m["match_type"] == "country_exposure"

    def test_site_countries_widen_the_candidate_search(self):
        index = matching.supplier_index([{"id": "a", "name": "Acme", "country_code": "DE", "sites": [KOBE]}])
        assert index["countries"] == ["DE", "JP"]

    def test_gdacs_point_is_stored(self):
        from intel_support import fixture
        feature = fixture("gdacs.json")["features"][0]
        signal = sources.parse_gdacs(feature)
        assert signal["raw"]["lat"] == feature["geometry"]["coordinates"][1]
        assert signal["raw"]["lon"] == feature["geometry"]["coordinates"][0]
        assert sources.parse_gdacs({**feature, "geometry": {"type": "Polygon", "coordinates": []}})["raw"].get("lat") is None
