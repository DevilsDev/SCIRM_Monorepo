"""Regulatory watch: which FDA and EMA records name a term on an organization's watchlist.

A term matches as whole words, ignoring case and punctuation, anywhere in a record's
title, summary or the substance and product fields its source provides. So "metformin"
matches "Metformin Hydrochloride Tablets" but not "metformina", and "immunoglobulin"
does not match "immunoglobulins" (watch the exact form the regulators use).
"""

import re
from typing import Any, Dict, Iterable, List

from libs.intel.sources import REGULATORY_SOURCES

KINDS = ("substance", "product")
MAX_ITEMS = 200

_NON_WORD = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", (text or "").lower()).split())


def clean_term(term: str) -> str:
    """The stored form of a term; raises ValueError with a message."""
    cleaned = " ".join((term or "").split())
    if not 3 <= len(normalize(cleaned)) <= 100:
        raise ValueError("A term needs 3 to 100 letters or digits.")
    return cleaned[:100]


def record_text(signal: Dict[str, Any]) -> str:
    raw = signal.get("raw") or {}
    parts = [signal.get("title") or "", signal.get("summary") or ""]
    for key in ("substances", "medicine", "generic_name", "product_description", "subject"):
        value = raw.get(key)
        parts.extend(value if isinstance(value, list) else [value] if isinstance(value, str) else [])
    return normalize(" ".join(str(p) for p in parts))


def matching_terms(signal: Dict[str, Any], terms: Iterable[str]) -> List[str]:
    """The watched terms a record names (in the order given)."""
    if signal.get("source") not in REGULATORY_SOURCES:
        return []
    text = f" {record_text(signal)} "
    return [t for t in terms if normalize(t) and f" {normalize(t)} " in text]


def like_patterns(terms: Iterable[str]) -> List[str]:
    """Broad SQL ILIKE prefilters (the first word of each term); matching_terms decides."""
    words = {normalize(t).split(" ")[0] for t in terms if normalize(t)}
    return [f"%{w}%" for w in sorted(words)]
