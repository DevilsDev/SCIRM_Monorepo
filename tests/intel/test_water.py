"""Water risk by site from WRI Aqueduct 4.0 (libs/intel/water.py and its committed data).

The expected values were checked against WRI's own polygons (the Aqueduct 4.0 GDB) with an
exact point-in-polygon test when the data was built.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from libs.intel import water  # noqa: E402

CAIRO = {"id": "s1", "label": "Cairo plant", "city": "Cairo", "country": "EG", "lat": 30.0444, "lon": 31.2357,
         "precision": "city", "source": "manual"}


def indicator(result, key):
    return next(i for i in result["indicators"] if i["key"] == key)


class TestLookup:
    def test_a_site_gets_its_unit_and_wris_own_labels(self):
        r = water.site_water_risk(CAIRO)
        assert r["status"] == "inside" and r["distance_km"] is None
        assert r["unit_country"] == "EGY" and r["province"] == "Al Qahirah" and r["country"] == "EG"
        assert indicator(r, "bws")["label"] == "Extremely High (>80%)" and indicator(r, "bws")["category"] == 4
        assert indicator(r, "rfr")["label"] == "High (6 in 1,000 to 1 in 100)"
        assert r["precision"] == "city" and r["label"] == "Cairo plant"

    @pytest.mark.parametrize("lat,lon,province,bws", [
        (34.6937, 135.5023, "Osaka", "Low - Medium (10-20%)"),
        (50.1109, 8.6821, "Hessen", "High (40-80%)"),
        (47.5596, 7.5886, "Basel-Stadt", "Low (<10%)"),
        (17.385, 78.4867, "Telangana", "Extremely High (>80%)"),
    ])
    def test_known_places(self, lat, lon, province, bws):
        r = water.site_water_risk({"lat": lat, "lon": lon})
        assert r["province"] == province and indicator(r, "bws")["label"] == bws

    def test_no_data_is_said_not_hidden(self):
        drought = indicator(water.site_water_risk(CAIRO), "drr")
        assert drought["category"] == water.CATEGORY_NO_DATA and drought["label"] == "No Data"
        assert drought["raw"] is None

    def test_every_indicator_and_projection_is_listed_separately(self):
        r = water.site_water_risk(CAIRO)
        assert [i["key"] for i in r["indicators"]] == list(water.INDICATORS)
        assert len(r["future_water_stress"]) == len(water.SCENARIOS) * len(water.YEARS)
        bau = next(f for f in r["future_water_stress"] if f["scenario"] == "bau" and f["year"] == "2030")
        assert bau["label"] == "Extremely high (>80%)"
        assert not any(k in r for k in ("score", "overall", "risk_score"))

    def test_a_point_just_off_the_coast_uses_the_nearest_unit_and_says_so(self):
        r = water.site_water_risk({"lat": 34.60, "lon": 135.35})  # Osaka Bay
        assert r["status"] == "nearest" and 0 < r["distance_km"] <= water.NEAREST_KM and r["province"] == "Osaka"

    def test_open_sea_and_missing_coordinates(self):
        assert water.site_water_risk({"lat": 0, "lon": -30})["status"] == "outside"
        assert water.site_water_risk({"label": "HQ", "country": "DE"})["status"] == "not_located"
        assert water.unit_at(95, 0) is None

    def test_wrapping_longitude(self):
        assert water.unit_at(-17.7, 178.0) is not None  # Fiji, east of the antimeridian
        assert water.unit_at(64.8, -179.9) is None or water.unit_at(64.8, -179.9)[0] > 0

    def test_supplier_lists_every_site(self):
        located = water.supplier_water_risk({"sites": [CAIRO, {"id": "s2", "label": "Office"}, "junk"]})
        assert [s["status"] for s in located] == ["inside", "not_located"]


class TestCatalogue:
    def test_source_and_licence_travel_with_the_data(self):
        c = water.catalog()
        assert c["source"]["licence"] == "CC BY 4.0" and "doi.org/10.46830/writn.23.00061" in c["source"]["citation"]
        assert {i["key"] for i in c["indicators"]} == set(water.INDICATORS)

    def test_composites_and_third_party_index_are_left_out(self):
        head, _ = water._units()
        assert not any(h.startswith("w_awr") or h.startswith("rri") for h in head)
