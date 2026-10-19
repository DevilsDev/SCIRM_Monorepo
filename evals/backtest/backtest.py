"""
Back-test: would recall history have flagged a firm before its next Class I recall?

At each monthly cutoff T, every firm with an FDA recall in the 3 years before T
is scored using only recalls *published* before T (libs/intel/scoring.py). The
outcome is whether the firm has a Class I recall (the most serious class)
published in the following HORIZON_DAYS.

- The alert threshold is chosen on the tuning period (cutoffs in 2021–2022) to
  flag about the top FLAG_SHARE of firms, then frozen. All headline numbers come
  from the later test period (2023 onward), which the threshold never saw.
- Firms are identified by normalized name (libs/intel/matching.py), so
  "SUN PHARMACEUTICAL INDUSTRIES INC" and "Sun Pharmaceutical Industries, Inc."
  count as one firm.
- Scope: firms that have had at least one recall. Firms with none are not in the
  data and cannot be scored. FDA shortage history is excluded because openFDA
  publishes only the current list, so past shortages that were resolved are
  missing and would bias the test.

    python evals/backtest/backtest.py [--json results.json]
"""

import argparse
import gzip
import json
import sys
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.intel import matching, scoring  # noqa: E402

DATA = Path(__file__).parent / "data" / "fda_enforcement.jsonl.gz"
HORIZON_DAYS = 90
# A Class I recall soon after another may be the same problem spreading, which is
# easy to "predict". Recall is also reported for firms without one in this window.
RECENT_DAYS = 180
UNIVERSE_YEARS = 3
FLAG_SHARE = 0.10
TUNE = (date(2021, 1, 1), date(2022, 12, 1))
TEST_START = date(2023, 1, 1)


@dataclass
class Event:
    published: date
    classification: Optional[str]


def _day(value: Optional[str]) -> Optional[date]:
    if value and len(value) == 8 and value.isdigit():
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    return None


def load(path: Path = DATA) -> Tuple[dict, List[dict]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        meta = json.loads(f.readline())
        return meta, [json.loads(line) for line in f if line.strip()]


def build_events(records: List[dict]) -> Dict[str, List[Event]]:
    """Per firm, one event per FDA event id: published when FDA first reported any
    of its recalls, classified by its most serious recall. Initiation dates are
    deliberately ignored: they precede publication."""
    grouped: Dict[Tuple[str, str], dict] = {}
    for r in records:
        firm = matching.normalize(r.get("recalling_firm") or "")
        published = _day(r.get("report_date"))
        if not firm or not published:
            continue
        key = (firm, str(r.get("event_id") or r.get("recall_number")))
        entry = grouped.setdefault(key, {"published": published, "classes": []})
        entry["published"] = min(entry["published"], published)
        entry["classes"].append(r.get("classification"))
    firms: Dict[str, List[Event]] = {}
    for (firm, _), entry in grouped.items():
        firms.setdefault(firm, []).append(Event(entry["published"], scoring.most_severe(entry["classes"])))
    for events in firms.values():
        events.sort(key=lambda e: e.published)
    return firms


def months(start: date, end: date) -> List[date]:
    out, d = [], date(start.year, start.month, 1)
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def observations(firms: Dict[str, List[Event]], cutoffs: List[date]) -> List[dict]:
    """One row per (firm, cutoff) in the universe: score known at T, outcome after T."""
    rows = []
    for firm, events in firms.items():
        dates = [e.published for e in events]
        for t in cutoffs:
            # In the universe: a recall published in the UNIVERSE_YEARS before T.
            lo = bisect_left(dates, t - timedelta(days=365 * UNIVERSE_YEARS))
            hi = bisect_left(dates, t)
            if lo == hi:
                continue
            past = [{"published": e.published, "classification": e.classification} for e in events[lo:hi]]
            future = [e for e in events[hi:] if e.published < t + timedelta(days=HORIZON_DAYS)
                      and e.classification == "Class I"]
            recent_class_i = any(e.classification == "Class I" and e.published >= t - timedelta(days=RECENT_DAYS)
                                 for e in events[lo:hi])
            rows.append({"firm": firm, "cutoff": t, "score": scoring.recall_history_score(past, t),
                         "outcome": bool(future), "recent_class_i": recent_class_i,
                         "warning_days": (future[0].published - t).days if future else None})
    return rows


def auc(rows: List[dict]) -> float:
    """Probability that a firm with the outcome scores above one without (ties count half)."""
    ranked = sorted(rows, key=lambda r: r["score"])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j]["score"] == ranked[i]["score"]:
            j += 1
        mean_rank = (i + 1 + j) / 2
        rank_sum += mean_rank * sum(r["outcome"] for r in ranked[i:j])
        i = j
    pos = sum(r["outcome"] for r in rows)
    neg = len(rows) - pos
    if not pos or not neg:
        return float("nan")
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def threshold_for_share(rows: List[dict], share: float) -> float:
    scores = sorted((r["score"] for r in rows), reverse=True)
    return scores[max(0, int(len(scores) * share) - 1)] if scores else 0.0


def evaluate(rows: List[dict], threshold: float) -> dict:
    flagged = [r for r in rows if r["score"] >= threshold and r["score"] > 0]
    positives = [r for r in rows if r["outcome"]]
    hits = [r for r in flagged if r["outcome"]]
    base = len(positives) / len(rows) if rows else 0.0
    precision = len(hits) / len(flagged) if flagged else 0.0
    new_problems = [r for r in positives if not r["recent_class_i"]]
    any_history = [r for r in rows if r["score"] > 0]
    any_hits = [r for r in any_history if r["outcome"]]
    return {
        "observations": len(rows),
        "firms": len({r["firm"] for r in rows}),
        "class_i_outcomes": len(positives),
        "base_rate": round(base, 4),
        "flagged": len(flagged),
        "flagged_share": round(len(flagged) / len(rows), 4) if rows else 0.0,
        "precision": round(precision, 4),
        "recall": round(len(hits) / len(positives), 4) if positives else 0.0,
        "lift": round(precision / base, 2) if base else None,
        "auc": round(auc(rows), 4),
        "median_warning_days": median(r["warning_days"] for r in hits) if hits else None,
        "new_problem_outcomes": len(new_problems),
        "new_problem_recall": round(sum(1 for r in new_problems if r["score"] >= threshold and r["score"] > 0)
                                    / len(new_problems), 4) if new_problems else 0.0,
        "baseline_any_recall_last_year": {
            "flagged_share": round(len(any_history) / len(rows), 4) if rows else 0.0,
            "precision": round(len(any_hits) / len(any_history), 4) if any_history else 0.0,
            "recall": round(len(any_hits) / len(positives), 4) if positives else 0.0,
        },
    }


def run(records: Optional[List[dict]] = None, snapshot_date: Optional[date] = None) -> dict:
    if records is None:
        meta, records = load()
        snapshot_date = date.fromisoformat(meta["snapshot_date"])
    firms = build_events(records)
    # The last cutoff must leave a full horizon before the snapshot, or late outcomes look negative.
    last_cutoff = (snapshot_date or date.today()) - timedelta(days=HORIZON_DAYS + 1)
    tune_rows = observations(firms, months(*TUNE))
    test_rows = observations(firms, months(TEST_START, last_cutoff))
    threshold = threshold_for_share(tune_rows, FLAG_SHARE)
    return {
        "question": f"Class I recall published within {HORIZON_DAYS} days of the cutoff, "
                    f"scored only from recalls published before it",
        "snapshot_date": snapshot_date.isoformat() if snapshot_date else None,
        "threshold": threshold,
        "tune": {"period": [TUNE[0].isoformat(), TUNE[1].isoformat()], **evaluate(tune_rows, threshold)},
        "test": {"period": [TEST_START.isoformat(), months(TEST_START, last_cutoff)[-1].isoformat()],
                 **evaluate(test_rows, threshold)},
    }


def report(result: dict) -> str:
    t = result["test"]
    b = t["baseline_any_recall_last_year"]
    return "\n".join([
        f"Back-test: {result['question']}",
        f"Data: openFDA recall snapshot of {result['snapshot_date']}; test cutoffs {t['period'][0]} to {t['period'][1]}",
        f"Universe: {t['firms']} firms with a recall in the prior {UNIVERSE_YEARS} years, "
        f"{t['observations']} firm-months, {t['class_i_outcomes']} with a Class I recall in the next {HORIZON_DAYS} days",
        f"Base rate: {t['base_rate']:.1%}",
        f"Score threshold (frozen from 2021-22): {result['threshold']:.3f} -> flags {t['flagged_share']:.1%} of firm-months",
        f"  precision {t['precision']:.1%}  recall {t['recall']:.1%}  lift {t['lift']}x  AUC {t['auc']:.3f}  "
        f"median warning {t['median_warning_days']} days",
        f"  {t['new_problem_outcomes']} of the {t['class_i_outcomes']} outcomes were at firms with no Class I recall "
        f"in the prior {RECENT_DAYS} days; recall on those: {t['new_problem_recall']:.1%}",
        f"Tuning period ({result['tune']['period'][0]}..{result['tune']['period'][1]}): precision {result['tune']['precision']:.1%}, "
        f"recall {result['tune']['recall']:.1%}, AUC {result['tune']['auc']:.3f}",
        f"Baseline 'any recall in the last year': flags {b['flagged_share']:.1%}, "
        f"precision {b['precision']:.1%}, recall {b['recall']:.1%}",
    ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, help="also write the full result as JSON")
    args = parser.parse_args()
    result = run()
    print(report(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
