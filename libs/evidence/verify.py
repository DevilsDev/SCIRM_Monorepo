"""
Citation checker: every factual sentence must cite records that support it.

A claim is kept only if:
- it cites at least one record, and every cited record exists;
- every date, FDA recall class, number and record type it states appears in a
  cited record;
- every company-like name it states (two or more capitalised words) appears in
  a cited record.

Anything else is removed before the user sees it. This is deterministic, so it
works without an LLM, and it is tested on answers corrupted on purpose
(evals/evidence). It checks that a claim's specifics come from its sources; it
cannot judge paraphrased reasoning. That is the job of the LLM reviewer planned
for when a model is configured.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_LONG = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})\b")
_MONTH_NAMES = re.compile(rf"\b({MONTHS})\b")
_CLASS = re.compile(r"\bClass\s+(III|II|I)\b")
_NUMBER = re.compile(r"(?<![\w.-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%?)(?![\w-])")
# Runs of two or more capitalised words. Connectors ("of", "and") are not bridged, so a
# firm and a product in one sentence ("Baxter Healthcare of STERILE WATER") stay separate.
_NAME = re.compile(r"\b[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*)+")
# Capitalised phrases that are not company names.
_NOT_NAMES = {"fda", "us", "u.s.", "usa", "red list", "green list", "class i", "class ii", "class iii", "gdacs",
              "not yet classified", "import alert", "warning letter"}
# Words an answer may use without finding them in the cited record: function words and
# the vocabulary of answer sentences. Any other word must come from the record, which
# catches a swapped company name however it is written ("TAME", "vitus pharm co ltd").
# Deliberately NOT free: negations (no, not, never), quantifiers (all, only, most),
# number words (one, three), and judgements (serious, minor, safe, problems). They can
# reverse or inflate what a record says ("FDA found no problems", "all products",
# "three recalls"), so they must appear in the record itself.
# A closed vocabulary rejects free paraphrase from an LLM; the answer then falls back to
# the records' own wording, which is the safe direction.
ANSWER_VOCABULARY = set("""
a an the and or of to in on at by for with from into as that this these those
it its they their them is are was were be been being has have had do does did
since until while when where which who whose there so may can could
fda gdacs us usa u.s united states food drug administration
recall recalls recalled published publish posted post reported report issued sent received listed lists
warning letter letters import alert alerts red list border detained detention without physical examination
shortage shortages discontinuation discontinued notice available unavailable limited availability presentations
presentation products product labeled labelled marketed distributed made manufactured
class unclassified disaster alert affecting affected about regarding concerning involving
""".split())

TYPE_WORDS = {"recall": "recall", "shortage": "shortage", "discontinu": "discontinuation",
              "warning letter": "warning_letter", "import alert": "import_alert", "red list": "import_alert"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def dates_in(text: str) -> List[str]:
    out = [f"{y}-{m}-{d}" for y, m, d in _ISO.findall(text)]
    out += [f"{y}-{int(m):02d}-{int(d):02d}" for m, d, y in _US.findall(text)]
    for month, day, year in _LONG.findall(text):
        out.append(datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date().isoformat())
    return out


def _numbers(text: str) -> List[str]:
    stripped = _ISO.sub(" ", _US.sub(" ", _LONG.sub(" ", text)))
    stripped = re.sub(r"\[S\d+\]", " ", stripped)
    stripped = re.sub(r"\b\d{1,2}-\d{2,3}\b", " ", stripped)  # import alert numbers like 66-40 are checked as text
    return [n.replace(",", "") + pct for n, pct in _NUMBER.findall(stripped)]


def passage_text(record: Dict[str, Any]) -> str:
    """Everything a claim may draw on from one record."""
    raw = record.get("raw") or {}
    parts = [record.get("title") or "", record.get("summary") or "", " ".join(record.get("entity_names") or []),
             " ".join(str(v) for v in raw.values() if v is not None), record.get("signal_type") or "",
             " ".join(record.get("country_codes") or [])]
    return " ".join(parts)


def _record_dates(record: Dict[str, Any]) -> set:
    found = {str(record.get(k))[:10] for k in ("published_at", "occurred_at", "updated_at") if record.get(k)}
    found |= set(dates_in(passage_text(record)))
    raw = record.get("raw") or {}
    for v in raw.values():
        if isinstance(v, str) and re.fullmatch(r"\d{8}", v):
            found.add(f"{v[:4]}-{v[4:6]}-{v[6:]}")
    return found


def check_claim(text: str, citations: List[str], evidence: Dict[str, Dict[str, Any]]) -> List[str]:
    """Reasons the claim is unsupported (empty list: supported).

    One cited record must support everything the claim states. Checking the union of
    several records would let a sentence pair one record's date with another's recall
    class, a statement neither record makes."""
    if not citations:
        return ["no citation"]
    missing = [c for c in citations if c not in evidence]
    if missing:
        return [f"cites unknown record {', '.join(missing)}"]
    best: Optional[List[str]] = None
    for c in citations:
        reasons = _unsupported(text, [evidence[c]])
        if not reasons:
            return []
        if best is None or len(reasons) < len(best):
            best = reasons
    return best or []


def _unsupported(text: str, cited: List[Dict[str, Any]]) -> List[str]:
    reasons = []
    body = " ".join(passage_text(r) for r in cited)
    body_norm = f" {_norm(body)} "
    known_dates = set().union(*(_record_dates(r) for r in cited))
    claim = re.sub(r"\[S\d+\]", " ", text)

    for d in dates_in(claim):
        if d not in known_dates:
            reasons.append(f"date {d} not in cited record")
    for cls in _CLASS.findall(claim):
        if not re.search(rf"\bClass\s+{cls}\b", body):
            reasons.append(f"Class {cls} not in cited record")
    body_numbers = set(_numbers(body)) | {n.lstrip("0") or "0" for n in _numbers(body)}
    for n in _numbers(claim):
        if n not in body_numbers and n.lstrip("0") not in body_numbers:
            reasons.append(f"number {n} not in cited record")
    claim_lower = claim.lower()
    cited_types = {r.get("signal_type") for r in cited}
    for word, kind in TYPE_WORDS.items():
        if word in claim_lower and kind not in cited_types and word not in body.lower():
            reasons.append(f"'{word}' does not describe the cited record")
    for name in _NAME.findall(claim):
        n = _norm(name)
        if n in _NOT_NAMES or len(n) < 4:
            continue
        if f" {n} " not in body_norm:
            reasons.append(f"name '{name}' not in cited record")
    body_words = set(body_norm.split())
    unknown = sorted({w for w in _norm(_MONTH_NAMES.sub(" ", claim)).split()
                      if w.isalpha() and len(w) > 1 and w not in body_words and w not in ANSWER_VOCABULARY})
    if unknown:
        reasons.append(f"words not in cited record: {', '.join(unknown[:5])}")
    return reasons


def verify(claims: List[Dict[str, Any]], evidence: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Split claims into kept and removed, with the reasons for each removal."""
    kept, removed = [], []
    for claim in claims:
        reasons = check_claim(claim.get("text") or "", list(claim.get("citations") or []), evidence)
        (removed if reasons else kept).append({**claim, "reasons": reasons} if reasons else claim)
    return {"claims": kept, "removed": removed}


def citations_in(text: str) -> List[str]:
    return re.findall(r"\[(S\d+)\]", text or "")


def split_sentences(text: str) -> List[Dict[str, Any]]:
    """Free text (e.g. from an LLM) into claims with their inline [S#] citations."""
    # Break after sentence punctuation or after a citation marker ("... Inc. [S1] The ..."),
    # so one supported sentence cannot shelter an unsupported one.
    sentences = re.split(r"(?<=[.!?\]])\s+(?=[A-Z])", (text or "").strip())
    return [{"text": s.strip(), "citations": citations_in(s)} for s in sentences if s.strip()]


def first_date(text: str) -> Optional[str]:
    found = dates_in(text)
    return found[0] if found else None
