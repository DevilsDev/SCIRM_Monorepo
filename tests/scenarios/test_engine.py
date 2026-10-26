"""The scenario engine: spend at risk per currency from real spend and stated safety stock."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from libs.scenarios import engine  # noqa: E402

A = {"id": "a", "name": "Alpha API", "spend_12m": {"EUR": "5200"}, "spend_main_currency": "EUR"}
B = {"id": "b", "name": "Beta US", "spend_12m": {"USD": "520"}, "spend_main_currency": "EUR"}
C = {"id": "c", "name": "Gamma Buffered", "spend_12m": {"EUR": "10400"}, "spend_main_currency": "EUR"}
COVERAGE = {"a": {"weeks": 2, "source": "supplier-provided", "single_source": True},
            "c": {"weeks": 10, "source": "supplier-provided", "single_source": False}}


def result(**kw):
    return engine.run([A, B, C], 4, COVERAGE, engine.main_currency([A, B, C]), **kw)


def test_spend_at_risk_per_currency_never_summed_across_currencies():
    r = result()
    assert r["main_currency"] == "EUR"
    assert r["interrupted"] == {"EUR": "1200.00", "USD": "40.00"}  # (5200 + 10400) x 4/52; 520 x 4/52
    assert r["at_risk"] == {"EUR": "200.00", "USD": "40.00"}  # A: 2 uncovered weeks; C fully covered
    assert r["suppliers_without_coverage_data"] == 1


def test_missing_coverage_counts_as_zero_and_says_so():
    beta = next(s for s in result()["suppliers"]["other_currencies"] if s["supplier_id"] == "b")
    assert beta["coverage_weeks"] is None and beta["uncovered_weeks"] == 4.0
    assert beta["coverage_source"].startswith("unknown")


def test_ranking_is_in_the_main_currency_others_listed_after():
    r = result()
    assert [s["supplier_id"] for s in r["suppliers"]["ranked"]] == ["a", "c"]
    assert [s["supplier_id"] for s in r["suppliers"]["other_currencies"]] == ["b"]


def test_the_plan_ranks_mitigations_by_reduction():
    r = result()
    ranked = [(m["supplier_id"], m["kind"], m["reduction"]) for m in r["plan"]["ranked"]]
    assert ranked == [("a", "safety_stock", {"EUR": "200.00"}), ("a", "second_source", {"EUR": "100.00"})]
    assert "single source" in r["plan"]["ranked"][1]["description"]
    assert [(m["supplier_id"], m["kind"]) for m in r["plan"]["other_currencies"]] == [("b", "safety_stock"), ("b", "second_source")]


def test_assumptions_change_the_plan_and_are_stated():
    r = result(stock_target_weeks=3, second_source_share=0.25)
    assert [m["reduction"] for m in r["plan"]["ranked"]] == [{"EUR": "100.00"}, {"EUR": "50.00"}]
    assert any("3 weeks" in a and "25%" in a for a in r["assumptions"])


def test_no_spend_no_main_currency():
    r = engine.run([{"id": "x", "name": "No SAP"}], 8, {}, engine.main_currency([{"id": "x"}]))
    assert r["main_currency"] is None and r["at_risk"] == {} and r["plan"] == {"ranked": [], "other_currencies": []}
