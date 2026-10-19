"""
Recall-history score: how much recent FDA recall activity a firm has, as of a date.

The weights are fixed in advance rather than fitted, so the back-test
(evals/backtest) measures them honestly. Only recalls *published* before
`as_of` count, because that is what someone could have known at the time.
"""

from datetime import date, timedelta
from typing import Any, Dict, Iterable, Optional

CLASS_WEIGHTS = {"Class I": 3.0, "Class II": 1.5, "Class III": 0.5}
HALF_LIFE_DAYS = 180
LOOKBACK_DAYS = 365
_SEVERITY_ORDER = ["Class III", "Class II", "Class I"]


def most_severe(classifications: Iterable[str]) -> Optional[str]:
    ranked = [c for c in classifications if c in CLASS_WEIGHTS]
    return max(ranked, key=_SEVERITY_ORDER.index) if ranked else None


def recall_history_score(events: Iterable[Dict[str, Any]], as_of: date) -> float:
    """`events`: one firm's recall events, each {"published": date, "classification": str}.

    One event may cover many products (one recall number each); callers pass one
    entry per event so a large batch counts once. Events published on or after
    `as_of`, or more than LOOKBACK_DAYS before it, are ignored.
    """
    start = as_of - timedelta(days=LOOKBACK_DAYS)
    score = 0.0
    for event in events:
        published = event["published"]
        if not (start <= published < as_of):
            continue
        age = (as_of - published).days
        score += CLASS_WEIGHTS.get(event.get("classification"), 0.0) * 0.5 ** (age / HALF_LIFE_DAYS)
    return round(score, 6)
