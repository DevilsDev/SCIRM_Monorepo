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
    baseline = result["variants"]["recalls"]
    test, event = baseline["test"], baseline["events"]["lead_30d"]
    listed = baseline["events_listed_products"]["lead_30d"]
    assert test["period"][0] == "2023-01-01"
    # Headline: distinct Class I events, judged 30 days before FDA published them.
    assert event["class_i_events"] >= 100
    assert event["recall"] >= 0.33            # among firms with recall history
    assert event["recall_all_events"] >= 0.15  # among all serious recalls
    # Supply-chain scope: recalls of FDA-listed drug products.
    assert listed["class_i_events"] >= 50 and listed["recall_all_events"] >= 0.28
    # Secondary, per firm-month.
    assert test["auc"] >= 0.65 and test["lift"] >= 3.0
    assert test["flagged_share"] <= 0.15
    # Adding warning letters must not make the headline worse.
    letters = result["variants"]["recalls+letters"]["events"]["lead_30d"]
    assert letters["recall_all_events"] >= event["recall_all_events"]
    print("\n" + backtest.report(result))


def test_threshold_comes_from_the_tuning_period_only(result):
    _, records, letters = backtest.load()
    firms = backtest.build_events(records, letters)
    for name, kinds in backtest.VARIANTS.items():
        tune_rows = backtest.observations(firms, backtest.months(*backtest.TUNE), kinds)
        assert result["variants"][name]["threshold"] == backtest.threshold_for_share(tune_rows, backtest.FLAG_SHARE)


def test_product_watch_threshold_is_the_back_tested_one(result):
    """The product flags suppliers with the threshold the back-test measured, not a hand-tuned one."""
    assert scoring.WATCH_THRESHOLD == result["variants"]["recalls"]["threshold"]


def test_each_event_is_judged_once_at_a_fixed_lead():
    """Event-level recall must count an event once, at the last cutoff >= lead days before publication."""
    history = backtest.Event(date(2023, 1, 10), classification="Class II")
    event = backtest.Event(date(2024, 3, 20), classification="Class I")
    firms = {"acme": [history, event]}
    # Cutoff for a 30-day lead: 2024-02-01 (last month start on or before 2024-02-19). History is 2023-01-10:
    # in the 3-year universe but outside the 365-day scoring window, so the score is 0 -> not flagged.
    result = backtest.event_level(firms, threshold=0.1, start=date(2024, 1, 1), end=date(2025, 1, 1), lead_days=30)
    assert (result["class_i_events"], result["events_with_history"], result["flagged"]) == (1, 1, 0)
    recent = {"acme": [backtest.Event(date(2024, 1, 15), classification="Class II"), event]}
    result = backtest.event_level(recent, threshold=0.1, start=date(2024, 1, 1), end=date(2025, 1, 1), lead_days=30)
    assert result["flagged"] == 1 and result["new_problem_events"] == 1
    # A recall published after the cutoff (inside the lead) must not count.
    late = {"acme": [backtest.Event(date(2023, 1, 10), classification="Class II"),
                     backtest.Event(date(2024, 3, 1), classification="Class II"), event]}
    result = backtest.event_level(late, threshold=0.1, start=date(2024, 1, 1), end=date(2025, 1, 1), lead_days=30)
    assert result["flagged"] == 0


class TestWarningLetters:
    def test_letters_count_from_their_posting_date(self):
        letter = {"company": "Acme Pharma Inc.", "posted_date": "2024-06-15", "letter_issue_date": "2024-05-01",
                  "severity": "high", "product_area": "drugs"}
        firms = backtest.build_events([record(report="20230801", event="h")], [letter])
        [row] = backtest.observations(firms, [T], ("recall", "warning_letter"))
        [recalls_only] = backtest.observations(firms, [T], ("recall",))
        assert row["score"] == recalls_only["score"], "a letter posted after the cutoff must not count"

    def test_food_and_device_letters_are_left_out_of_the_drug_back_test(self):
        food = {"company": "Acme Pharma Inc.", "posted_date": "2024-05-01", "severity": "high", "product_area": "food"}
        firms = backtest.build_events([record(report="20230801", event="h")], [food])
        assert [e.kind for e in firms["acme pharma"]] == ["recall"]

    def test_a_letter_alone_puts_a_firm_in_the_letters_universe(self):
        letter = {"company": "Acme Pharma Inc.", "posted_date": "2024-05-01", "severity": "high", "product_area": "drugs"}
        firms = backtest.build_events([], [letter])
        assert backtest.observations(firms, [T], ("recall",)) == []
        [row] = backtest.observations(firms, [T], ("recall", "warning_letter"))
        assert row["score"] > 0
