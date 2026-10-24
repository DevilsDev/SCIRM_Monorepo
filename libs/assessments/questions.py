"""Questionnaires for supplier assessments: the built-in templates, checks on questions and
on a supplier's answers, and the score.

The score is computed here, from yes/no questions that say which answer is the good one
(`good`) and how much it matters (`weight`, 1 to 5). It is the weighted share of those
questions answered the good way, out of those answered. Answers the other way are listed
as flags. Everything a supplier enters is the supplier's own statement: it is shown as
supplier-provided and never treated as a finding.
"""

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

TYPES = ("yes_no", "text", "number", "date", "choice", "subtier")
MAX_QUESTIONS = 60
MAX_TEXT = 4000
MAX_LINKS = 50
_ID = re.compile(r"[a-z0-9_]{1,40}")
_COUNTRY = re.compile(r"[A-Za-z]{2}")


def _q(qid: str, text: str, qtype: str, required: bool = False, good: Optional[str] = None, weight: int = 1,
       options: Optional[List[str]] = None, help: str = "") -> Dict[str, Any]:
    q: Dict[str, Any] = {"id": qid, "text": text, "type": qtype, "required": required, "help": help}
    if good:
        q.update(good=good, weight=weight)
    if options:
        q["options"] = options
    return q


BUILT_IN: Dict[str, Dict[str, Any]] = {
    "builtin:continuity": {
        "id": "builtin:continuity", "built_in": True, "name": "Supply continuity",
        "description": "Built-in template: business continuity, single sources, stock and the supplier's own "
                       "critical suppliers.",
        "questions": [
            _q("bcp", "Do you have a documented business continuity plan that covers the products you supply to us?",
               "yes_no", True, "yes", 3),
            _q("bcp_tested", "Has that plan been tested in the last 12 months?", "yes_no", False, "yes", 2),
            _q("single_site", "Is any product you supply to us made at only one site?", "yes_no", True, "no", 3),
            _q("single_site_detail", "If so, which products, and is a second site qualified or planned?", "text"),
            _q("single_source", "Do you rely on a single source for any active ingredient or critical raw material "
                                "used in our products?", "yes_no", True, "no", 3),
            _q("safety_stock_weeks", "How many weeks of finished-goods safety stock do you hold for our products?",
               "number"),
            _q("disruption", "Have you had a supply disruption that affected customers in the last 24 months?",
               "yes_no", True, "no", 2),
            _q("disruption_detail", "If yes, what happened and what changed afterwards?", "text"),
            _q("subtier", "Your critical suppliers for the products you supply to us", "subtier",
               help="The companies you buy active ingredients, key materials or services from: name, country, "
                    "and what they supply."),
        ],
    },
    "builtin:quality": {
        "id": "builtin:quality", "built_in": True, "name": "Quality and compliance",
        "description": "Built-in template: GMP status, inspections, recalls and change notification.",
        "questions": [
            _q("gmp", "Do the sites that supply us hold a current GMP certificate or equivalent?", "yes_no", True,
               "yes", 3),
            _q("last_inspection", "Date of the most recent regulatory inspection of the main site", "date"),
            _q("inspection_outcome", "Outcome of that inspection", "choice", True,
               options=["No observations", "Observations (for example an FDA Form 483)",
                        "Warning letter or equivalent", "Not inspected"]),
            _q("open_capa", "Are corrective actions from an inspection or audit still open?", "yes_no", False, "no", 2),
            _q("recall", "Have you recalled a product in the last 36 months?", "yes_no", True, "no", 2),
            _q("change_notice", "Do you notify customers before changing a site, a process or a key supplier?",
               "yes_no", True, "yes", 3),
            _q("data_integrity", "Do you run a data integrity program (for example ALCOA+)?", "yes_no", False,
               "yes", 1),
        ],
    },
}


def validate_questions(raw: Any) -> List[Dict[str, Any]]:
    """A template's questions, checked and normalised. Raises ValueError with a message."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("Add at least one question.")
    if len(raw) > MAX_QUESTIONS:
        raise ValueError(f"A questionnaire can have at most {MAX_QUESTIONS} questions.")
    out, seen = [], set()
    for n, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Question {n} is not valid.")
        qid = str(item.get("id") or f"q{n}").strip().lower()
        text = str(item.get("text") or "").strip()
        qtype = item.get("type")
        if not _ID.fullmatch(qid) or qid in seen:
            raise ValueError(f"Question {n} needs a unique id (lowercase letters, digits, _).")
        if not 1 <= len(text) <= 500:
            raise ValueError(f"Question {n} needs a text of up to 500 characters.")
        if qtype not in TYPES:
            raise ValueError(f"Question {n} has an unknown type; use one of {', '.join(TYPES)}.")
        seen.add(qid)
        good = item.get("good") if qtype == "yes_no" else None
        if good not in (None, "", "yes", "no"):
            raise ValueError(f"Question {n}: the good answer must be yes or no.")
        options = None
        if qtype == "choice":
            options = [str(o).strip()[:200] for o in item.get("options") or [] if str(o).strip()]
            if not 2 <= len(options) <= 20 or len(set(options)) != len(options):
                raise ValueError(f"Question {n} needs 2 to 20 different options.")
        weight = item.get("weight", 1)
        if good and (not isinstance(weight, int) or isinstance(weight, bool) or not 1 <= weight <= 5):
            raise ValueError(f"Question {n}: the weight must be a whole number from 1 to 5.")
        out.append(_q(qid, text, qtype, bool(item.get("required")), good or None, weight if good else 1,
                      options, str(item.get("help") or "").strip()[:300]))
    return out


def _link(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        raise ValueError("Each supplier needs a name.")
    name = str(raw.get("name") or "").strip()[:200]
    country = str(raw.get("country") or raw.get("country_code") or "").strip()
    if not name:
        if any(str(raw.get(k) or "").strip() for k in ("country", "city", "supplies")):
            raise ValueError("Each supplier needs a name.")
        return None  # an empty row in the form
    if country and not _COUNTRY.fullmatch(country):
        raise ValueError(f"Use a two-letter country code for {name} (for example DE or IN).")
    return {"name": name, "country_code": country.upper() or None,
            "city": str(raw.get("city") or "").strip()[:100] or None,
            "supplies": str(raw.get("supplies") or "").strip()[:200] or None}


def clean_answers(questions: List[Dict[str, Any]], raw: Any, final: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """The supplier's answers, checked against the questions, and the sub-tier suppliers
    they listed. A draft may be incomplete; a final submission must answer every required
    question. Unknown question ids are ignored. Raises ValueError with a message."""
    if not isinstance(raw, dict):
        raise ValueError("Answers are not valid.")
    answers: Dict[str, Any] = {}
    links: List[Dict[str, Any]] = []
    for q in questions:
        value = raw.get(q["id"])
        if value is None or (isinstance(value, str) and not value.strip()) or value == []:
            if final and q.get("required"):
                raise ValueError(f"Answer: {q['text']}")
            continue
        kind = q["type"]
        if kind == "yes_no":
            if value not in ("yes", "no"):
                raise ValueError(f"Answer yes or no: {q['text']}")
        elif kind == "text":
            value = str(value).strip()[:MAX_TEXT]
        elif kind == "number":
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"Enter a number: {q['text']}")
            if value != value or abs(value) > 1e12:
                raise ValueError(f"Enter a number: {q['text']}")
        elif kind == "date":
            try:
                value = date.fromisoformat(str(value)).isoformat()
            except ValueError:
                raise ValueError(f"Enter a date (YYYY-MM-DD): {q['text']}")
        elif kind == "choice":
            if value not in (q.get("options") or []):
                raise ValueError(f"Pick one of the options: {q['text']}")
        elif kind == "subtier":
            if not isinstance(value, list) or len(value) > MAX_LINKS:
                raise ValueError(f"List up to {MAX_LINKS} suppliers.")
            value = [link for link in (_link(item) for item in value) if link]
            if not value:
                if final and q.get("required"):
                    raise ValueError(f"Answer: {q['text']}")
                continue
            links.extend(value)
        answers[q["id"]] = value
    return answers, links


def score(questions: List[Dict[str, Any]], answers: Dict[str, Any]) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    """(score 0-100 or None when no scored question was answered, flags)."""
    total = good = 0
    flags = []
    for q in questions:
        if q.get("type") != "yes_no" or not q.get("good") or answers.get(q["id"]) not in ("yes", "no"):
            continue
        weight = int(q.get("weight") or 1)
        total += weight
        if answers[q["id"]] == q["good"]:
            good += weight
        else:
            flags.append({"id": q["id"], "text": q["text"], "answer": answers[q["id"]], "weight": weight})
    flags.sort(key=lambda f: -f["weight"])
    return (round(100 * good / total) if total else None), flags
