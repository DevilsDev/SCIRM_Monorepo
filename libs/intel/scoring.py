"""
Regulatory-history score: how much recent FDA enforcement activity a firm has, as of a date.

The weights are fixed in advance rather than fitted, so the back-test
(evals/backtest) measures them honestly. Only events *published* before `as_of`
count, because that is what someone could have known at the time.
"""

from datetime import date, timedelta
from typing import Any, Dict, Iterable, Optional

# Recalls, by FDA class.
CLASS_WEIGHTS = {"Class I": 3.0, "Class II": 1.5, "Class III": 0.5}
# Warning letters: a manufacturing-practice (CGMP) finding weighs between a Class II
# and a Class I recall; other violations (e.g. marketing claims) less.
WARNING_LETTER_WEIGHTS = {"high": 2.0, "medium": 1.0}
HALF_LIFE_DAYS = 180
LOOKBACK_DAYS = 365
# Recall-history score at or above which a supplier is flagged "watch". This is the
# threshold the back-test froze on 2022 (top 10% of firms) and measured on 2023 onward;
# tests/intel/test_intel_backtest.py fails if the two drift apart. Warning letters are
# shown but not scored: in the back-test they added two flagged events in 145 while
# adding two thirds more flags.
WATCH_THRESHOLD = 1.90677
_SEVERITY_ORDER = ["Class III", "Class II", "Class I"]


def most_severe(classifications: Iterable[str]) -> Optional[str]:
    ranked = [c for c in classifications if c in CLASS_WEIGHTS]
    return max(ranked, key=_SEVERITY_ORDER.index) if ranked else None


def event_weight(event: Dict[str, Any]) -> float:
    kind = event.get("kind", "recall")
    if kind == "recall":
        return CLASS_WEIGHTS.get(event.get("classification"), 0.0)
    if kind == "warning_letter":
        return WARNING_LETTER_WEIGHTS.get(event.get("severity"), WARNING_LETTER_WEIGHTS["medium"])
    return 0.0


def regulatory_history_score(events: Iterable[Dict[str, Any]], as_of: date,
                             kinds: Iterable[str] = ("recall", "warning_letter")) -> float:
    """`events`: one firm's events, each {"published": date, "kind": "recall"|"warning_letter",
    "classification" (recalls) or "severity" (warning letters)}.

    Pass one entry per recall *event* (an FDA event may cover many products), so a
    large batch counts once. Events published on or after `as_of`, or more than
    LOOKBACK_DAYS before it, are ignored.
    """
    kinds = set(kinds)
    start = as_of - timedelta(days=LOOKBACK_DAYS)
    score = 0.0
    for event in events:
        if event.get("kind", "recall") not in kinds:
            continue
        published = event["published"]
        if not (start <= published < as_of):
            continue
        score += event_weight(event) * 0.5 ** ((as_of - published).days / HALF_LIFE_DAYS)
    return round(score, 6)


def recall_history_score(events: Iterable[Dict[str, Any]], as_of: date) -> float:
    """Recalls only: the original baseline rule."""
    return regulatory_history_score(events, as_of, kinds=("recall",))
