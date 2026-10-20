"""
Supplier-name matching, measured on a labelled set of real company strings from
openFDA recall and shortage records.

Ground truth is "a risk manager tracking this supplier would want this record":
the same company, or one that names it as parent or trade name. A false match
tells a customer their supplier had a recall it never had, so precision must be
perfect on this set. Recall may be lower, and the misses are listed explicitly.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from libs.intel import matching  # noqa: E402

THRESHOLD = 0.6

SAME_COMPANY = [
    ("Sun Pharmaceutical Industries, Inc.", "SUN PHARMACEUTICAL INDUSTRIES INC"),
    ("Sun Pharmaceutical Industries, Inc.", "Sun Pharmaceutical Industries Ltd."),
    ("Teva Pharmaceuticals USA, Inc.", "Teva Pharmaceuticals USA"),
    ("Teva Pharmaceuticals USA, Inc.", "Teva Pharmaceuticals USA Inc"),
    ("Apotex Corp.", "Apotex Inc."),
    ("Aurobindo Pharma USA Inc.", "Aurobindo Pharma USA Inc"),
    ("Zydus Pharmaceuticals (USA) Inc", "Zydus Pharmaceuticals USA Inc"),
    ("Cipla USA, Inc.", "CIPLA"),
    ("Cipla USA, Inc.", "Cipla Limited"),
    ("Pfizer Inc.", "PFIZER, INC"),
    ("Pfizer Inc.", "Hospira, Inc., a Pfizer Company"),
    ("Hospira, Inc.", "Hospira, Inc., a Pfizer Company"),
    ("Hikma Pharmaceuticals USA Inc.", "Hikma Pharmaceuticals USA INC."),
    ("Hikma Pharmaceuticals USA Inc.", "Hikma Injectables USA Inc"),
    ("Mylan Pharmaceuticals Inc", "MYLAN PHARMACEUTICALS INC"),
    ("Mylan Institutional, Inc.", "Mylan Institutional, Inc. (d.b.a. UDL Laboratories)"),
    ("UDL Laboratories", "Mylan Institutional, Inc. (d.b.a. UDL Laboratories)"),
    ("Mylan Pharmaceuticals Inc", "Mylan Institutional LLC"),
    ("Dr. Reddy's Laboratories, Inc.", "Dr Reddy's Laboratories Limited"),
    ("B. Braun Medical Inc.", "B BRAUN MEDICAL INC"),
    ("B. Braun Medical Inc.", "B. Braun Medical, Inc."),
    ("Akorn, Inc.", "Akorn Inc"),
    ("Sandoz Inc", "Sandoz, Inc"),
    ("Nephron SC, LLC", "Nephron Sc Inc"),
    ("Fresenius Kabi USA, LLC", "Fresenius Kabi USA LLC"),
    ("Baxter Healthcare", "Baxter Healthcare Corporation"),
    ("Amneal Pharmaceuticals, LLC", "Amneal Pharmaceuticals of New York, LLC"),
    ("Essential Wellness Pharma", "Kalman Health & Wellness, Inc. dba Essential Wellness Pharma"),
    ("Major Pharmaceuticals", "The Harvard Drug Group LLC dba Major Pharmaceuticals and Rugby Laboratories"),
    ("Par Pharmaceutical Inc.", "Par Pharmaceutical, Inc."),
    ("Perrigo Company PLC", "Perrigo Company"),
]

DIFFERENT_COMPANY = [
    ("Fresenius Kabi USA, LLC", "Fresenius Medical Care Holdings, Inc."),
    ("Fresenius Kabi USA, LLC", "Fresenius Medical Care, North America"),
    ("Global Pharma Healthcare Private Limited", "Global Corporation"),
    ("Global Pharma Healthcare Private Limited", "Global Sanitizers LLC"),
    ("Global Pharma Healthcare Private Limited", "GLOBAL WIDGET LLC"),
    ("B. Braun Medical Inc.", "B & B Pharmaceuticals, Inc."),
    ("B. Braun Medical Inc.", "B AND A TRADING CORPORATION"),
    ("Dr. Reddy's Laboratories, Inc.", "Dr. Berne's Whole Health Products"),
    ("American Regent, Inc.", "American Health Packaging"),
    ("American Regent, Inc.", "American Screening LLC"),
    ("Advanced Accelerator Applications USA, Inc.", "Advanced Pharmaceutical Technology, Inc."),
    ("Advanced Accelerator Applications USA, Inc.", "Advanced Nutriceuticals, LLC"),
    ("Par Pharmaceutical Inc.", "Pharma Nobis LLC"),
    ("Leading Pharma, LLC", "Pharma Nobis LLC"),
    ("Pfizer Inc.", "Precision Dose Inc."),
    ("Hikma Pharmaceuticals USA Inc.", "Hospira, Inc., a Pfizer Company"),
    ("Teva Pharmaceuticals USA, Inc.", "Sandoz Inc"),
    ("Mylan Pharmaceuticals Inc", "Medinatura New Mexico, inc."),
    ("Akorn, Inc.", "ACME UNITED CORPORATION"),
    ("Amneal Pharmaceuticals, LLC", "American Regent, Inc."),
    ("Baxter Healthcare Corporation", "B. Braun Medical Inc."),
]

# Same corporate group, but the names alone don't say so. Missing these is the
# price of never inventing a match; supplier aliases are the way to catch them.
KNOWN_MISSES = {
    ("Hikma Pharmaceuticals USA Inc.", "Hikma Injectables USA Inc"),
    ("Mylan Pharmaceuticals Inc", "Mylan Institutional LLC"),
    ("Amneal Pharmaceuticals, LLC", "Amneal Pharmaceuticals of New York, LLC"),
    ("Major Pharmaceuticals", "The Harvard Drug Group LLC dba Major Pharmaceuticals and Rugby Laboratories"),
}


def matches(supplier_name: str, record_name: str, aliases=()) -> bool:
    found = matching.match_supplier({"name": supplier_name, "aliases": list(aliases)},
                                    {"entity_names": [record_name], "signal_type": "recall"})
    return bool(found) and found["confidence"] >= THRESHOLD


def test_precision_is_perfect_on_the_labelled_set():
    false_matches = [pair for pair in DIFFERENT_COMPANY if matches(*pair)]
    assert not false_matches


def test_recall_and_known_misses():
    missed = {pair for pair in SAME_COMPANY if not matches(*pair)}
    assert missed == KNOWN_MISSES, "a change in what is missed must be deliberate: update KNOWN_MISSES"
    recall = 1 - len(missed) / len(SAME_COMPANY)
    print(f"\nmatching on {len(SAME_COMPANY)} same / {len(DIFFERENT_COMPANY)} different pairs: "
          f"precision 1.00, recall {recall:.2f}")
    assert recall >= 0.85


def test_aliases_recover_a_known_miss():
    assert matches("Hikma Pharmaceuticals USA Inc.", "Hikma Injectables USA Inc", aliases=["Hikma Injectables"])


@pytest.mark.parametrize("raw, names, parents", [
    ("Hospira, Inc., a Pfizer Company", ["hospira"], ["pfizer"]),
    ("Zydus Pharmaceuticals (USA) Inc", ["zydus pharmaceutical"], []),
    ("Mylan Institutional, Inc. (d.b.a. UDL Laboratories)", ["udl laboratory", "mylan institutional"], []),
    ("Harvard Drug Group LLC d/b/a Major Pharmaceuticals", ["harvard drug group", "major pharmaceutical"], []),
    ("Glenmark Pharmaceuticals Inc., USA", ["glenmark pharmaceutical"], []),
])
def test_name_variants(raw, names, parents):
    assert matching.name_variants(raw) == {"names": names, "parents": parents}


def test_match_types_are_reported():
    assert matching.match_supplier({"name": "Pfizer Inc."}, {"entity_names": ["Hospira, Inc., a Pfizer Company"]}
                                   )["match_type"] == "parent_company"
    exact = matching.match_supplier({"name": "Apotex Corp."}, {"entity_names": ["Apotex Inc."]})
    assert exact["match_type"] == "name_exact" and exact["kind"] == "incident"


def test_single_word_names_match_with_lower_confidence():
    # A supplier entered by its short name: plausible, but "Baxter" alone could be another Baxter.
    found = matching.match_supplier({"name": "Baxter"}, {"entity_names": ["Baxter Healthcare Corporation"]})
    assert found and found["confidence"] < matching.CONFIDENCE["name_contains"]


def test_country_alone_is_an_exposure_never_an_incident():
    supplier = {"name": "Gland Pharma Limited", "country_code": "IN"}
    flood = {"entity_names": [], "country_codes": ["IN", "BD"], "signal_type": "disaster"}
    found = matching.match_supplier(supplier, flood)
    assert found["kind"] == "exposure" and found["match_type"] == "country_exposure"
    # A recall elsewhere in the same country says nothing about this supplier.
    assert matching.match_supplier(supplier, {"entity_names": ["Annora Pharma Private Limited"],
                                              "country_codes": ["IN"], "signal_type": "recall"}) is None
