"""
Link public signals to a tenant's suppliers.

Company names in public records are inconsistent ("SUN PHARMACEUTICAL INDUSTRIES
INC", "Sun Pharmaceutical Industries, Inc."), so names are normalized before
comparison. A wrong match tells a customer that their supplier had a recall it
never had, so the rules prefer missing a match to inventing one:

- every match says how it was made (`match_type`) and how sure it is;
- names made only of generic words ("Global Pharma Ltd") must match exactly;
- a match on country alone is labelled `exposure`, never an incident.
"""

import difflib
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "plc", "gmbh", "ag", "sa", "spa", "bv", "nv",
    "co", "corp", "corporation", "company", "pvt", "private", "kk", "oy", "ab", "as", "srl", "sarl",
    "pty", "lp", "llp", "pte", "se", "kg", "kgaa", "sas", "doo", "sro", "zoo",
}
# Trailing qualifiers that name a subsidiary's market rather than a different company.
GEO_QUALIFIERS = {"usa", "us", "america", "north"}
# Words too common in this industry to identify a company on their own.
GENERIC_WORDS = {
    "pharma", "pharmaceutical", "pharmaceuticals", "healthcare", "health", "medical", "lab", "labs",
    "laboratory", "laboratories", "industries", "industry", "group", "holdings", "holding", "global",
    "international", "biotech", "bio", "therapeutics", "life", "sciences", "science", "products",
    "services", "solutions", "distribution", "drug", "drugs", "chemical", "chemicals", "technologies",
    "technology", "manufacturing", "and", "of", "the", "care", "specialty", "generics", "outsourcing",
    "supplier", "suppliers",
}
_STEMS = {"pharmaceuticals": "pharmaceutical", "laboratories": "laboratory", "labs": "lab",
          "industries": "industry", "chemicals": "chemical", "sciences": "science",
          "technologies": "technology", "holdings": "holding", "products": "product"}

# Confidence by match type; the threshold for showing a match is the caller's choice.
CONFIDENCE = {"name_exact": 0.95, "name_contains": 0.8, "name_similar": 0.7, "parent_company": 0.6,
              "country_exposure": 0.4}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _tokens(text: str) -> List[str]:
    text = _ascii(text).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [_STEMS.get(t, t) for t in text.split()]
    while tokens and tokens[0] == "the":
        tokens = tokens[1:]
    # Strip legal suffixes and market qualifiers from the end, repeatedly ("Teva Pharmaceuticals USA, Inc").
    while len(tokens) > 1 and (tokens[-1] in LEGAL_SUFFIXES or tokens[-1] in GEO_QUALIFIERS):
        tokens = tokens[:-1]
    return tokens


def name_variants(raw: str) -> Dict[str, List[str]]:
    """Split a raw company string into its own names and parent names.

    "Hospira, Inc., a Pfizer Company"  -> names ["hospira"], parents ["pfizer"]
    "F.H. INVESTMENTS, Inc. (dba Asteria Health)" -> names ["asteria health", "f h investments"]
    """
    names: List[str] = []
    parents: List[str] = []
    # Spell out "d.b.a." / "d/b/a" as "dba" so the alias rules below see one form.
    text = re.sub(r"(?<![a-z])d\s*[./]\s*b\s*[./]\s*a(?![a-z])\.?", "dba", _ascii(raw or ""), flags=re.I)
    for alias in re.findall(r"\((?:dba|aka|formerly)\s+([^)]*)\)", text, flags=re.I):
        names.append(alias)
    text = re.sub(r"\([^)]*\)", " ", text)  # other parentheticals, e.g. "(USA)"
    parent = re.search(r",?\s+(?:a|an)\s+(.+?)\s+(?:company|subsidiary|business)\b.*$", text, flags=re.I)
    if parent:
        parents.append(parent.group(1))
        text = text[: parent.start()]
    for part in re.split(r"\s+(?:dba|aka)\s+", text, flags=re.I):
        names.append(part)
    norm = lambda items: [n for n in dict.fromkeys(" ".join(_tokens(i)) for i in items) if n]
    return {"names": norm(names), "parents": norm(parents)}


def normalize(raw: str) -> str:
    variants = name_variants(raw)["names"]
    return variants[0] if variants else ""


def is_distinctive(normalized: str) -> bool:
    return any(t not in GENERIC_WORDS and t not in LEGAL_SUFFIXES and len(t) > 1 for t in normalized.split())


def match_key(normalized: str) -> Optional[str]:
    """The first distinctive token: a cheap index for finding candidate signals."""
    for token in normalized.split():
        if token not in GENERIC_WORDS and len(token) >= 3:
            return token
    return None


def entity_keys(raw_names: Iterable[str]) -> List[str]:
    keys: Set[str] = set()
    for raw in raw_names:
        variants = name_variants(raw)
        for n in variants["names"] + variants["parents"]:
            key = match_key(n)
            if key:
                keys.add(key)
    return sorted(keys)


def compare_names(supplier: str, entity: str) -> Optional[str]:
    """Match type for two normalized names, or None."""
    if not supplier or not entity:
        return None
    if supplier == entity:
        return "name_exact"
    if not (is_distinctive(supplier) and is_distinctive(entity)):
        return None
    s, e = supplier.split(), entity.split()
    # One name extends the other with generic words only ("baxter healthcare" vs "baxter
    # healthcare corporation" after suffixes, "b braun medical" vs "b braun"), sharing the first token.
    shorter, longer = (s, e) if len(s) <= len(e) else (e, s)
    if longer[: len(shorter)] == shorter and all(t in GENERIC_WORDS for t in longer[len(shorter):]):
        return "name_contains"
    # Small spelling differences ("glenmark pharmaceutical" / "glenmark pharmaceutics").
    if s[0] == e[0] and difflib.SequenceMatcher(None, supplier, entity).ratio() >= 0.92:
        return "name_similar"
    return None


def _aliases(supplier: Dict[str, Any]) -> List[str]:
    """Other names the supplier trades under (stored with the supplier as `aliases`)."""
    aliases = supplier.get("aliases") or (supplier.get("metadata") or {}).get("aliases") or []
    return [a for a in aliases if isinstance(a, str)][:20]


def match_supplier(supplier: Dict[str, Any], signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best match between one supplier and one signal, or None."""
    names = [supplier.get("name") or ""] + _aliases(supplier)
    supplier_names = [n for raw in names for n in name_variants(raw)["names"]]

    best: Optional[Dict[str, Any]] = None
    for raw in signal.get("entity_names") or []:
        variants = name_variants(raw)
        for kind, candidates in (("own", variants["names"]), ("parent", variants["parents"])):
            for entity in candidates:
                for own in supplier_names:
                    match_type = compare_names(own, entity)
                    if match_type and kind == "parent":
                        match_type = "parent_company"
                    if not match_type:
                        continue
                    confidence = CONFIDENCE[match_type]
                    if match_type == "name_contains" and min(len(own.split()), len(entity.split())) == 1:
                        confidence = 0.65  # "Sterling" could be any of several Sterlings
                    if best is None or confidence > best["confidence"]:
                        best = {"match_type": match_type, "confidence": confidence,
                                "kind": "incident", "matched_on": raw}
    if best:
        return best
    country = (supplier.get("country_code") or "").upper()
    if country and country in (signal.get("country_codes") or []) and signal.get("signal_type") == "disaster":
        return {"match_type": "country_exposure", "confidence": CONFIDENCE["country_exposure"],
                "kind": "exposure", "matched_on": country}
    return None


def supplier_index(suppliers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Keys and countries to fetch candidate signals for these suppliers."""
    keys: Set[str] = set()
    for s in suppliers:
        keys.update(entity_keys([s.get("name") or ""] + _aliases(s)))
    countries = sorted({(s.get("country_code") or "").upper() for s in suppliers if s.get("country_code")})
    return {"keys": sorted(keys), "countries": countries}


def match_all(suppliers: List[Dict[str, Any]], signals: List[Dict[str, Any]],
              min_confidence: float = 0.0) -> Dict[str, List[Dict[str, Any]]]:
    """Matches per supplier id, strongest first."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for supplier in suppliers:
        found = []
        for signal in signals:
            m = match_supplier(supplier, signal)
            if m and m["confidence"] >= min_confidence:
                found.append({**m, "signal": signal})
        found.sort(key=lambda m: (m["confidence"], m["signal"].get("published_at") or ""), reverse=True)
        out[str(supplier.get("id"))] = found
    return out
