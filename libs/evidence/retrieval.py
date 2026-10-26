"""
Keyword retrieval over public signals, scoped to one supplier.

v1 is keyword search only (PostgreSQL full text). Vector search is planned once an
embedding provider is chosen; it is not simulated here.

Buyers phrase questions differently from FDA records ("sterility problems" vs
"Lack of Assurance of Sterility"), so the question is read for three things:

- **Record type** ("warning letter", "held at the border", "dropping products"):
  only records of that type are returned.
- **Topic**, mapped to the vocabulary FDA uses in recall reasons, letter subjects and
  alert titles. Named hazards (nitrosamine, potency, labelling) are *specific*;
  broad ones (contamination, manufacturing quality) are *general*. A record must
  contain a term of the most specific topic asked about, so a question about
  nitrosamine is not answered with an unrelated contamination recall.
- **Other content words** (product names, for example) only raise the ranking.

A question with no type and no topic ("anything I should worry about?") returns
the supplier's records by severity, then recency.

Results are filtered with the same supplier matcher as everywhere else
(libs/intel/matching.py), so the engine never cites a record the supplier view
would not show.
"""

import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from libs.intel import matching

logger = structlog.get_logger()

MIN_CONFIDENCE = 0.6
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Question words that carry no type or topic.
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "at", "from", "about", "as", "is",
    "are", "was", "were", "be", "been", "has", "have", "had", "do", "does", "did", "any", "anything", "something",
    "there", "their", "they", "them", "it", "its", "this", "that", "these", "those", "what", "which", "who", "whom",
    "when", "where", "why", "how", "can", "could", "should", "would", "will", "shall", "may", "might", "must", "i",
    "we", "our", "us", "me", "my", "you", "your", "know", "tell", "show", "give", "list", "find", "see",
    "recent", "recently", "latest", "lately", "ever", "past", "last", "year", "years", "month", "months", "new",
    "current", "currently", "now", "still", "yet", "all", "some", "many", "much", "more", "most", "other", "else",
    "issue", "issues", "problem", "problems", "trouble", "troubles", "concern", "concerns", "concerned", "worry",
    "worried", "worrying", "risk", "risks", "risky", "safe", "reliable", "trust", "okay", "fine", "good", "serious",
    "major", "big", "bad", "happen", "happened", "happening", "went", "supplier", "suppliers", "vendor", "vendors",
    "partner", "company", "firm", "manufacturer", "fda", "regulator", "regulatory", "public", "record", "records",
    "news", "info", "information", "status", "situation", "update", "updates", "flag", "flags", "flagged", "watch",
    "product", "products", "item", "items", "goods", "drug", "drugs", "medicine", "medicines", "pharma", "anyone",
    "really", "please", "maybe", "being", "into", "over", "under", "out", "off", "up", "down", "than", "then", "also",
}

# (word prefixes in the question, record types they ask for, search terms)
TYPE_INTENTS: List[Tuple[Tuple[str, ...], Set[str], List[str]]] = [
    (("recall",), {"recall"}, ["recall"]),
    (("letter", "enforce", "warn", "reprimand"), {"warning_letter"}, ["warning letter"]),
    (("border", "import", "detain", "detent", "customs", "bar", "ban", "blocked", "embargo", "refus"),
     {"import_alert"}, ["import alert", "detained", "border", "detention"]),
    (("shortag", "stock", "supply", "supplies", "availab", "unavailab", "backorder", "back-order", "scarc", "obtain",
      "runout", "running"), {"shortage"}, ["shortage", "unavailable", "limited availability"]),
    (("discontinu", "dropping", "drop", "phase", "phasing", "away", "exit", "exiting", "cease", "ceasing", "longer",
      "withdraw", "retir", "sunset", "axe", "axing"), {"discontinuation"}, ["discontinuation", "discontinued"]),
    (("disast", "earthquak", "quake", "flood", "storm", "cyclon", "hurrican", "typhoon", "weather", "drought",
      "wildfir", "volcan"), {"disaster"}, ["earthquake", "flood", "cyclone", "tropical", "drought", "wildfire", "volcano"]),
]

# (word prefixes, specific?, search terms). Specific topics name a defect; general ones a broad area.
TOPICS: List[Tuple[Tuple[str, ...], bool, List[str]]] = [
    (("impur", "carcino", "cancer", "nitros", "ndma", "ndea", "ndsri", "benzene", "toxic"), True,
     ["impurity", "impurities", "nitrosamine", "nitroso", "ndma", "ndea", "ndsri", "benzene", "carcinogen"]),
    (("potenc", "strong", "weak", "strength", "subpot", "superpot", "assay", "dose", "dosing", "uniformity"), True,
     ["subpotent", "superpotent", "potency", "assay", "uniformity"]),
    (("dissol", "dissolv"), True, ["dissolution"]),
    (("label", "mislabel", "misbrand", "mixup", "mix-up", "labell"), True,
     ["label", "labeling", "labeled", "mislabeled", "misbranded", "labelling"]),
    (("unapprov", "approv", "signed", "authoriz", "authoris", "licens", "illegal", "unlicens"), True,
     ["unapproved", "unlicensed", "new drug"]),
    (("particl", "particul", "glass", "fiber", "fibre", "metal", "shard"), True, ["particulate", "particles", "glass"]),
    (("packag", "container", "vial", "seal", "leak", "crack", "closure", "bottle", "syringe", "bag", "pouch"), True,
     ["packaging", "container", "closure", "leak", "leaking", "vial", "cracked", "bag", "seal"]),
    (("stabil", "degrad", "expir", "shelf"), True, ["stability", "degradation", "expiry", "expiration"]),
    (("crush", "broken", "break", "chip", "split", "crumbl", "physical", "defect", "damag"), True,
     ["crushed", "broken", "chipped", "split", "defective", "damaged", "physical"]),
    (("steril", "asept", "contamin", "microb", "bacteri", "fung", "mold", "mould", "germ", "dirty", "endotox",
      "infect", "pyrogen"), False,
     ["sterility", "sterile", "aseptic", "microbial", "contamination", "contaminated", "bacterial", "endotoxin"]),
    (("manufact", "quality", "gmp", "cgmp", "practice", "facility", "facilities", "plant", "factory", "inspect",
      "deviat", "standard", "process", "control"), False,
     ["cgmp", "gmp", "manufacturing", "adulterated", "deviations"]),
]


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", (text or "").lower())


# Phrases that ask about entering the US market (import alerts), where single words
# would be ambiguous ("did they ship mislabeled bags?" is not about the border).
IMPORT_PHRASES = re.compile(r"\b(?:ship\w*|sell\w*|export\w*|get\w*|enter\w*)\s+(?:\w+\s+){0,2}"
                            r"(?:into|to|in)\s+(?:the\s+)?(?:us|u\.s\.?|usa|united states|america|american market)\b",
                            re.IGNORECASE)


def _hits(word: str, trigger: str) -> bool:
    """Prefix match for longer triggers; whole-word forms only for short ones
    ("bar" matches "barred" but not "barcode", "ban" not "bandage")."""
    if len(trigger) >= 5:
        return word.startswith(trigger)
    return word in {trigger, trigger + "s", trigger + "ed", trigger + trigger[-1] + "ed", trigger + "ing",
                    trigger + trigger[-1] + "ing"}


def query_terms(question: str, supplier_name: str = "") -> Dict[str, Any]:
    """How a question will be searched: record types, topics and extra content words."""
    supplier_words = set(_words(supplier_name)) | set(matching.normalize(supplier_name).split())
    content = [w for w in _words(question) if w not in STOPWORDS and w not in supplier_words and len(w) > 2]
    types: Set[str] = set()
    type_terms: List[str] = []
    specific: List[str] = []
    general: List[str] = []
    used: Set[str] = set()
    if IMPORT_PHRASES.search(question or ""):
        types.add("import_alert")
        type_terms += ["import alert", "detained", "border", "detention"]
    for word in content:
        for triggers, kinds, terms in TYPE_INTENTS:
            if any(_hits(word, t) for t in triggers):
                types |= kinds
                type_terms += terms
                used.add(word)
        for triggers, is_specific, terms in TOPICS:
            if any(_hits(word, t) for t in triggers):
                (specific if is_specific else general).extend(terms)
                used.add(word)
    extra = [w for w in content if w not in used]
    required = list(dict.fromkeys(specific or general))
    terms = list(dict.fromkeys(required + type_terms + extra))
    return {"types": sorted(types), "required": required, "specific": bool(specific), "extra": extra,
            "terms": terms}


def _text(record: Dict[str, Any]) -> str:
    """A record's text for topic matching, without its company names: "sterility" must
    not match "Acme Sterile Products Inc." just because of the firm's name."""
    raw = record.get("raw") or {}
    text = " ".join([record.get("title") or "", record.get("summary") or ""] +
                    [str(v) for v in raw.values() if v is not None]).lower()
    for name in sorted({n.lower() for n in (record.get("entity_names") or []) if n}, key=len, reverse=True):
        text = text.replace(name, " ")
    for key in ("recalling_firm", "company", "company_name", "firm"):
        if raw.get(key):
            text = text.replace(str(raw[key]).lower(), " ")
    return text


def _contains_any(text: str, terms: List[str]) -> bool:
    """Whether the text has any term, as a phrase or as a word prefix (rough stemming)."""
    words = set(re.findall(r"[a-z0-9]+", text))
    for term in terms:
        if " " in term:
            if term in text:
                return True
        elif any(w.startswith(term[:6]) for w in words):
            return True
    return False


def _supplier_matches(supplier: Dict[str, Any], records: List[Dict[str, Any]], include_exposures: bool):
    out = []
    for record in records:
        m = matching.match_supplier(supplier, record)
        if not m or (m["kind"] == "incident" and m["confidence"] < MIN_CONFIDENCE):
            continue
        if m["kind"] == "exposure" and not include_exposures:
            continue
        out.append((record, m))
    return out


# Vector hits farther than this (cosine distance) are not evidence of relevance. Not yet
# calibrated: set it from a held-out evaluation once real embeddings run (evals/evidence).
VECTOR_MAX_DISTANCE = float(os.getenv("EMBED_MAX_DISTANCE", "0.55"))
RRF_K = 60  # reciprocal rank fusion constant


def _key(record: Dict[str, Any]) -> Tuple[str, str]:
    return (record["source"], record["external_id"])


async def _vector_ranked(store, embedder, question: str, supplier: Dict[str, Any], keys: List[str],
                         types: Set[str]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """The supplier's records nearest to the question, within the distance cut-off and
    the requested record types. An embedding failure leaves keyword results only."""
    try:
        query = await embedder.embed_query(question)
        hits = await store.vector_search(query, embedder.model_id, keys, limit=50)
    except Exception as exc:  # e.g. Bedrock throttling
        logger.warning("Vector search unavailable", error=type(exc).__name__)
        return []
    hits = [h for h in hits if h["distance"] <= VECTOR_MAX_DISTANCE and (not types or h["signal_type"] in types)]
    return _supplier_matches(supplier, hits, include_exposures=False)


def _fuse(*rankings: List[Tuple[Dict[str, Any], Dict[str, Any]]]):
    """Reciprocal rank fusion: a record high in either list ranks high overall."""
    scores: Dict[Tuple[str, str], float] = {}
    items: Dict[Tuple[str, str], Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for ranking in rankings:
        for rank, (record, m) in enumerate(ranking, 1):
            key = _key(record)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            items.setdefault(key, (record, m))
    return sorted(items.values(), key=lambda rm: (scores[_key(rm[0])], SEVERITY_RANK.get(rm[0]["severity"], 0),
                                                 rm[0].get("updated_at") or rm[0]["published_at"]), reverse=True)


def _one_per_event_first(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each event's best-ranked record first, in rank order; then the rest, in rank order.
    One FDA recall event is often a dozen records (one per strength or pack), which would
    otherwise fill the top results and hide the supplier's other events. Nothing is dropped."""
    seen, first, rest = set(), [], []
    for item in results:
        key = matching.event_key(item["record"])
        (rest if key in seen else first).append(item)
        seen.add(key)
    return first + rest


async def retrieve(store, question: str, supplier: Dict[str, Any], k: int = 10, embedder=None) -> Dict[str, Any]:
    """The supplier's records most relevant to the question, plus how they were found.
    With an embedder, keyword and vector results are fused; without one, keyword only."""
    parsed = query_terms(question, supplier.get("name") or "")
    index = matching.supplier_index([supplier])
    types, required = set(parsed["types"]), parsed["required"]
    disasters = "disaster" in types

    if types or required:
        found = await store.search_signals(parsed["terms"], keys=index["keys"], limit=1000) if parsed["terms"] else []
        if types and not required:
            # A pure type question ("any warning letters?") wants all of that type, ranked or not.
            found += [s for s in await store.signal_candidates(index["keys"], [], limit=5000)
                      if s["signal_type"] in types]
        if disasters and index["countries"]:
            found += [s for s in await store.signal_candidates([], index["countries"], limit=1000)
                      if s["signal_type"] == "disaster"]
        candidates = [r for r in found
                      if (not types or r["signal_type"] in types) and (not required or _contains_any(_text(r), required))]
        ranked = _supplier_matches(supplier, candidates, include_exposures=disasters)
        extra = parsed["extra"]
        ranked.sort(key=lambda rm: (_contains_any(_text(rm[0]), extra) if extra else False, rm[0].get("rank") or 0,
                                    SEVERITY_RANK.get(rm[0]["severity"], 0),
                                    rm[0].get("updated_at") or rm[0]["published_at"]), reverse=True)
        mode = "keyword"
        if embedder is not None and not (types and not required):
            vector = await _vector_ranked(store, embedder, question, supplier, index["keys"], types)
            if vector:
                ranked, mode = _fuse(ranked, vector), "hybrid"
    else:
        found = await store.signal_candidates(index["keys"], [], limit=5000)
        ranked = _supplier_matches(supplier, found, include_exposures=False)
        # Other words (a product name, say): if some records contain them, those are the answer.
        named = [rm for rm in ranked if parsed["extra"] and _contains_any(_text(rm[0]), parsed["extra"])]
        if named:
            ranked, mode = named, "named"
        elif parsed["extra"] and embedder is not None:
            # A described problem keyword search cannot parse ("bits floating in the liquid"):
            # meaning-based search, and nothing if nothing is close enough.
            ranked, mode = await _vector_ranked(store, embedder, question, supplier, index["keys"], set()), "vector"
        else:
            mode = "general"
        if mode != "vector":
            ranked.sort(key=lambda rm: (SEVERITY_RANK.get(rm[0]["severity"], 0),
                                        rm[0].get("updated_at") or rm[0]["published_at"]), reverse=True)
    seen, unique = set(), []
    for record, m in ranked:
        key = _key(record)
        if key not in seen:
            seen.add(key)
            unique.append({"record": record, "match": m})
    unique = _one_per_event_first(unique)
    return {"mode": mode, "types": parsed["types"], "terms": parsed["terms"], "required": required,
            "total": len(unique), "results": unique[:k]}


async def supplier_record_count(store, supplier: Dict[str, Any]) -> int:
    """All active records naming the supplier (for "none of its N records match")."""
    index = matching.supplier_index([supplier])
    found = await store.signal_candidates(index["keys"], [], limit=5000)
    return len(_supplier_matches(supplier, found, include_exposures=False))
