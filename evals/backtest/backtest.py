"""
Back-test: would regulatory history have flagged a firm before its next Class I recall?

At each monthly cutoff T, every firm with FDA history in the 3 years before T is
scored using only events *published* before T (libs/intel/scoring.py). The
outcome is whether the firm has a Class I recall (the most serious class)
published afterwards. Two variants are measured the same way:

- "recalls": recall history only (the original baseline)
- "recalls+letters": recalls plus FDA warning letters about drugs and biologics,
  by their posting date (food, device and veterinary letters are left out: the
  outcome is a drug recall, which those firms cannot have)

Rules that keep the numbers honest:

- **No tuning on the answers.** Each variant's alert threshold is chosen on the
  tuning period (cutoffs in 2022) to flag the top FLAG_SHARE of firms, then
  frozen. Headline numbers come from 2023 onward. 2022 is the first year with a
  full year of warning-letter history (FDA's index starts in January 2021).
- **One firm, many spellings.** Firms are identified by normalized name
  (libs/intel/matching.py), across both sources.
- **Scope.** Firms with no FDA recall or warning letter are not in the data and
  cannot be scored. Shortages and import alerts are excluded: FDA publishes only
  their current lists, so entries removed in the past are missing, and which
  entries survived depends on what happened later.

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
from typing import Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.intel import matching, scoring  # noqa: E402

DATA = Path(__file__).parent / "data"
RECALLS = DATA / "fda_enforcement.jsonl.gz"
LETTERS = DATA / "fda_warning_letters.jsonl.gz"
HORIZON_DAYS = 90
UNIVERSE_YEARS = 3
FLAG_SHARE = 0.10
TUNE = (date(2022, 1, 1), date(2022, 12, 1))
TEST_START = date(2023, 1, 1)
# A Class I recall soon after another may be the same problem spreading, which is
# easy to "predict". Recall is also reported for firms without one in this window.
RECENT_DAYS = 180
LEADS = (30, 60)
BACKTEST_LETTER_AREAS = ("drugs", "biologics")
VARIANTS = {"recalls": ("recall",), "recalls+letters": ("recall", "warning_letter")}


@dataclass
class Event:
    published: date
    kind: str = "recall"
    classification: Optional[str] = None  # recalls
    severity: Optional[str] = None  # warning letters
    listed: bool = False  # recall of an FDA-listed drug product (has an NDC)

    def as_dict(self) -> dict:
        return {"published": self.published, "kind": self.kind, "classification": self.classification,
                "severity": self.severity}


def _ymd(value: Optional[str]) -> Optional[date]:
    if value and len(value) == 8 and value.isdigit():
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    return None


def _load(path: Path) -> Tuple[dict, List[dict]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        meta = json.loads(f.readline())
        return meta, [json.loads(line) for line in f if line.strip()]


def load() -> Tuple[dict, List[dict], List[dict]]:
    meta, recalls = _load(RECALLS)
    _, letters = _load(LETTERS) if LETTERS.exists() else ({}, [])
    return meta, recalls, letters


def build_events(records: List[dict], letters: Iterable[dict] = ()) -> Dict[str, List[Event]]:
    """Per firm: one event per FDA recall event id (published when FDA first reported
    any of its recalls, classed by its most serious recall) and one per warning
    letter (published when FDA posted it). Initiation and letter-issue dates are
    deliberately ignored: they precede publication."""
    grouped: Dict[Tuple[str, str], dict] = {}
    for r in records:
        firm = matching.normalize(r.get("recalling_firm") or "")
        published = _ymd(r.get("report_date"))
        if not firm or not published:
            continue
        key = (firm, str(r.get("event_id") or r.get("recall_number")))
        entry = grouped.setdefault(key, {"published": published, "classes": [], "listed": False})
        entry["published"] = min(entry["published"], published)
        entry["classes"].append(r.get("classification"))
        entry["listed"] = entry["listed"] or bool(r.get("listed_product"))
    firms: Dict[str, List[Event]] = {}
    for (firm, _), entry in grouped.items():
        firms.setdefault(firm, []).append(Event(entry["published"], "recall", scoring.most_severe(entry["classes"]),
                                                listed=entry["listed"]))
    for letter in letters:
        if letter.get("product_area") not in BACKTEST_LETTER_AREAS:
            continue
        firm = matching.normalize(letter.get("company") or "")
        if firm and letter.get("posted_date"):
            firms.setdefault(firm, []).append(Event(date.fromisoformat(letter["posted_date"]), "warning_letter",
                                                    severity=letter.get("severity")))
    for events in firms.values():
        events.sort(key=lambda e: e.published)
    return firms


def months(start: date, end: date) -> List[date]:
    out, d = [], date(start.year, start.month, 1)
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def _window(events: List[Event], kinds: Tuple[str, ...], t: date) -> List[Event]:
    """This firm's events of the given kinds published in the UNIVERSE_YEARS before t."""
    dates = [e.published for e in events]
    lo = bisect_left(dates, t - timedelta(days=365 * UNIVERSE_YEARS))
    hi = bisect_left(dates, t)
    return [e for e in events[lo:hi] if e.kind in kinds]


def _score(past: List[Event], t: date, kinds: Tuple[str, ...]) -> float:
    return scoring.regulatory_history_score([e.as_dict() for e in past], t, kinds=kinds)


def observations(firms: Dict[str, List[Event]], cutoffs: List[date], kinds: Tuple[str, ...] = ("recall",)) -> List[dict]:
    """One row per (firm, cutoff) in the universe: score known at T, outcome after T."""
    rows = []
    for firm, events in firms.items():
        for t in cutoffs:
            past = _window(events, kinds, t)
            if not past:
                continue
            future = [e for e in events if t <= e.published < t + timedelta(days=HORIZON_DAYS)
                      and e.kind == "recall" and e.classification == "Class I"]
            recent_class_i = any(e.kind == "recall" and e.classification == "Class I"
                                 and e.published >= t - timedelta(days=RECENT_DAYS) for e in past)
            rows.append({"firm": firm, "cutoff": t, "score": _score(past, t, kinds), "outcome": bool(future),
                         "recent_class_i": recent_class_i})
    return rows


def auc(rows: List[dict]) -> float:
    """Probability that a firm with the outcome scores above one without (ties count half)."""
    ranked = sorted(rows, key=lambda r: r["score"])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j]["score"] == ranked[i]["score"]:
            j += 1
        rank_sum += (i + 1 + j) / 2 * sum(r["outcome"] for r in ranked[i:j])
        i = j
    pos = sum(r["outcome"] for r in rows)
    neg = len(rows) - pos
    if not pos or not neg:
        return float("nan")
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def threshold_for_share(rows: List[dict], share: float) -> float:
    scores = sorted((r["score"] for r in rows), reverse=True)
    return scores[max(0, int(len(scores) * share) - 1)] if scores else 0.0


def _share(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


def evaluate(rows: List[dict], threshold: float, n_months: int) -> dict:
    flagged = [r for r in rows if r["score"] >= threshold and r["score"] > 0]
    positives = [r for r in rows if r["outcome"]]
    hits = [r for r in flagged if r["outcome"]]
    base = len(positives) / len(rows) if rows else 0.0
    precision = len(hits) / len(flagged) if flagged else 0.0
    return {
        "observations": len(rows), "firms": len({r["firm"] for r in rows}),
        "class_i_outcomes": len(positives), "base_rate": round(base, 4),
        "flagged": len(flagged), "flagged_share": _share(len(flagged), len(rows)),
        "flags_per_month": round(len(flagged) / n_months, 1) if n_months else 0.0,
        "precision": round(precision, 4), "lift": round(precision / base, 2) if base else None,
        "auc": round(auc(rows), 4),
    }


def last_month_start_before(day: date) -> date:
    return date(day.year, day.month, 1)


def event_level(firms: Dict[str, List[Event]], threshold: float, start: date, end: date, lead_days: int,
                kinds: Tuple[str, ...] = ("recall",), listed_only: bool = False) -> dict:
    """Per distinct Class I recall event published in [start, end): was the firm flagged at
    the last monthly cutoff at least `lead_days` before FDA published it?

    `listed_only` keeps recalls of FDA-listed drug products: what pharma buyers source.
    Most other Class I "drug" recalls are tainted supplements sold online."""
    total = with_history = flagged = new_total = new_flagged = 0
    no_history_listed = no_history_unlisted = 0
    for events in firms.values():
        for e in events:
            if e.kind != "recall" or e.classification != "Class I" or not (start <= e.published < end):
                continue
            if listed_only and not e.listed:
                continue
            total += 1
            cutoff = last_month_start_before(e.published - timedelta(days=lead_days))
            past = _window(events, kinds, cutoff)
            if not past:
                # No history at the cutoff: the firm cannot be scored. Unlisted products here
                # are mostly supplements sold as drugs online, not pharma suppliers.
                no_history_listed += e.listed
                no_history_unlisted += not e.listed
                continue
            with_history += 1
            score = _score(past, cutoff, kinds)
            hit = score >= threshold and score > 0
            flagged += hit
            if not any(p.kind == "recall" and p.classification == "Class I"
                       and p.published >= cutoff - timedelta(days=RECENT_DAYS) for p in past):
                new_total += 1
                new_flagged += hit
    return {"lead_days": lead_days, "class_i_events": total, "events_with_history": with_history,
            "flagged": flagged, "recall": _share(flagged, with_history), "recall_all_events": _share(flagged, total),
            "new_problem_events": new_total, "new_problem_recall": _share(new_flagged, new_total),
            "no_history_listed_products": no_history_listed, "no_history_unlisted_products": no_history_unlisted}


def run_variant(firms: Dict[str, List[Event]], kinds: Tuple[str, ...], snapshot_date: date) -> dict:
    # The last cutoff must leave a full horizon before the snapshot, or late outcomes look negative.
    last_cutoff = snapshot_date - timedelta(days=HORIZON_DAYS + 1)
    tune_cutoffs, test_cutoffs = months(*TUNE), months(TEST_START, last_cutoff)
    tune_rows = observations(firms, tune_cutoffs, kinds)
    test_rows = observations(firms, test_cutoffs, kinds)
    threshold = threshold_for_share(tune_rows, FLAG_SHARE)
    return {
        "kinds": list(kinds),
        "threshold": threshold,
        "tune": {"period": [TUNE[0].isoformat(), TUNE[1].isoformat()],
                 **evaluate(tune_rows, threshold, len(tune_cutoffs))},
        "test": {"period": [TEST_START.isoformat(), test_cutoffs[-1].isoformat()],
                 **evaluate(test_rows, threshold, len(test_cutoffs))},
        # Headline: distinct Class I events, each judged once at a fixed lead before publication.
        "events": {f"lead_{lead}d": event_level(firms, threshold, TEST_START + timedelta(days=lead), snapshot_date,
                                                lead, kinds) for lead in LEADS},
        # Diagnostic only: recalls openFDA links to a listed product (NDC). Not a clean
        # "pharma supplier" scope: it also drops real manufacturers' recalls that openFDA
        # did not link (e.g. Novartis, Pfizer, Baxter), so it is not a headline.
        "events_listed_products": {
            f"lead_{lead}d": event_level(firms, threshold, TEST_START + timedelta(days=lead), snapshot_date, lead,
                                         kinds, listed_only=True) for lead in LEADS},
    }


def run(records: Optional[List[dict]] = None, letters: Optional[List[dict]] = None,
        snapshot_date: Optional[date] = None) -> dict:
    if records is None:
        meta, records, letters = load()
        snapshot_date = date.fromisoformat(meta["snapshot_date"])
    snapshot_date = snapshot_date or date.today()
    firms = build_events(records, letters or [])
    return {
        "question": "Class I recall published after the cutoff, scored only from events published before it",
        "snapshot_date": snapshot_date.isoformat(),
        "variants": {name: run_variant(firms, kinds, snapshot_date) for name, kinds in VARIANTS.items()},
    }


def report(result: dict) -> str:
    lines = [
        "Back-test: was a firm flagged before its Class I recall, using only events published earlier?",
        f"Data snapshot {result['snapshot_date']}; thresholds frozen from 2022 (top {FLAG_SHARE:.0%} of firms); "
        f"results from 2023 on",
    ]
    for name, v in result["variants"].items():
        t = v["test"]
        lines += ["", f"[{name}]"]
        for e in v["events"].values():
            lines.append(
                f"  {e['lead_days']}d ahead: {e['class_i_events']} Class I events. {e['events_with_history']} at firms with "
                f"FDA history: {e['flagged']} flagged ({e['recall']:.1%}); new problems {e['new_problem_recall']:.1%} of "
                f"{e['new_problem_events']}. {e['class_i_events'] - e['events_with_history']} at firms with no history "
                f"({e['no_history_unlisted_products']} unlisted products, {e['no_history_listed_products']} listed drugs). "
                f"Overall {e['recall_all_events']:.1%}")
        lines.append(
            f"  per firm-month: {t['firms']} firms, {t['flags_per_month']} flags/month ({t['flagged_share']:.1%}), "
            f"precision {t['precision']:.1%} ({t['lift']}x base rate {t['base_rate']:.1%}), AUC {t['auc']:.3f}")
    return "\n".join(lines)


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
