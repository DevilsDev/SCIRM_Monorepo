"""
The back-test must never use information that was not public at the cutoff,
or its numbers overstate what the product can do.
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from libs.intel import scoring  # noqa: E402

spec = importlib.util.spec_from_file_location("scirm_backtest", ROOT / "evals" / "backtest" / "backtest.py")
backtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backtest)

T = date(2024, 6, 1)


def record(firm="Acme Pharma Inc.", cls="Class II", report="20240501", initiated=None, event="e1", number="D-1"):
    return {"recalling_firm": firm, "classification": cls, "report_date": report,
            "recall_initiation_date": initiated or report, "event_id": event, "recall_number": number}


def rows_for(records, cutoff=T):
    return {r["firm"]: r for r in backtest.observations(backtest.build_events(records), [cutoff])}


class TestPointInTime:
    def test_recall_initiated_before_but_published_after_the_cutoff_is_not_known(self):
        history = record(report="20230101", event="old")
        late = record(cls="Class I", report="20240615", initiated="20240401", event="late", number="D-2")
        row = rows_for([history, late])["acme pharma"]
        expected = scoring.recall_history_score([], T)  # the 2023 recall is outside the 365-day window
        assert row["score"] == expected == 0.0
        assert row["outcome"] is True  # ...but it is the outcome to predict

    def test_published_on_the_cutoff_day_is_not_known(self):
        on_day = record(report="20240601")
        assert scoring.recall_history_score([{"published": T, "classification": "Class I"}], T) == 0.0
        history = record(report="20230701", event="u")
        assert rows_for([history, on_day])["acme pharma"]["score"] == rows_for([history])["acme pharma"]["score"]

    def test_outcome_window_is_horizon_days_after_the_cutoff(self):
        base = record(report="20240101", event="h")
        inside = record(cls="Class I", report="20240829", event="in", number="D-3")   # T + 89 days
        outside = record(cls="Class I", report="20240830", event="out", number="D-4")  # T + 90 days
        assert rows_for([base, inside])["acme pharma"]["outcome"] is True
        assert rows_for([base, outside])["acme pharma"]["outcome"] is False

    def test_only_class_i_counts_as_the_outcome(self):
        rows = rows_for([record(report="20240101", event="h"), record(cls="Class II", report="20240701", event="n")])
        assert rows["acme pharma"]["outcome"] is False

    def test_firms_without_prior_recalls_are_outside_the_universe(self):
        assert rows_for([record(cls="Class I", report="20240701")]) == {}


class TestEvents:
    def test_a_batch_of_recalls_in_one_event_counts_once(self):
        batch = [record(report="20240501", number=f"D-{i}") for i in range(10)]
        single = [record(report="20240501")]
        assert rows_for(batch)["acme pharma"]["score"] == rows_for(single)["acme pharma"]["score"]

    def test_an_event_takes_its_most_serious_class(self):
        mixed = [record(cls="Class III", number="D-1"), record(cls="Class I", number="D-2")]
        [event] = backtest.build_events(mixed)["acme pharma"]
        assert event.classification == "Class I"

    def test_name_variants_are_one_firm(self):
        events = backtest.build_events([record(firm="SUN PHARMACEUTICAL INDUSTRIES INC", event="a"),
                                        record(firm="Sun Pharmaceutical Industries, Inc.", event="b")])
        assert list(events) == ["sun pharmaceutical industry"] and len(events["sun pharmaceutical industry"]) == 2


class TestScore:
    def test_recent_and_serious_scores_higher(self):
        recent = scoring.recall_history_score([{"published": date(2024, 5, 1), "classification": "Class II"}], T)
        older = scoring.recall_history_score([{"published": date(2023, 9, 1), "classification": "Class II"}], T)
        serious = scoring.recall_history_score([{"published": date(2024, 5, 1), "classification": "Class I"}], T)
        assert serious > recent > older > 0


def test_auc():
    rows = lambda pairs: [{"score": s, "outcome": o} for s, o in pairs]
    assert backtest.auc(rows([(1, False), (2, True)])) == 1.0
    assert backtest.auc(rows([(2, False), (1, True)])) == 0.0
    assert backtest.auc(rows([(1, False), (1, True)])) == 0.5


@pytest.fixture(scope="module")
def result():
    return backtest.run()


def test_committed_snapshot_result(result):
    """Regression guard on the committed data. If this fails after a scoring change,
    the change made the product worse at its main job; refreshed data may move it slightly."""
    test = result["test"]
    assert test["period"][0] == "2023-01-01"
    assert test["auc"] >= 0.65
    assert test["lift"] >= 3.0
    assert test["recall"] >= 0.35
    assert test["flagged_share"] <= 0.15
    print("\n" + backtest.report(result))


def test_threshold_comes_from_the_tuning_period_only(result):
    tune_rows = backtest.observations(backtest.build_events(backtest.load()[1]), backtest.months(*backtest.TUNE))
    assert result["threshold"] == backtest.threshold_for_share(tune_rows, backtest.FLAG_SHARE)
