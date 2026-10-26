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
       options: Optional[List[str]] = None, help: str = "", flag_only: bool = False) -> Dict[str, Any]:
    q: Dict[str, Any] = {"id": qid, "text": text, "type": qtype, "required": required, "help": help}
    if good:
        q.update(good=good, weight=weight)
    if flag_only:
        q["flag_only"] = True
    if options:
        q["options"] = options
    return q


def _dd(qid: str, text: str, good: str, refs: str, weight: int = 3) -> Dict[str, Any]:
    """A due-diligence question: the answer is the supplier's claim, so it can raise a flag
    for someone to follow up but never counts toward a score."""
    return _q(qid, text, "yes_no", True, good, weight, help=refs, flag_only=True)


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
    "builtin:due_diligence": {
        "id": "builtin:due_diligence", "built_in": True, "due_diligence": True,
        "name": "Human rights and environment",
        "description": "Built-in template for the in-depth step of due diligence (LkSG, CSDDD): the supplier's "
                       "own statements on labour, safety, wages, environment and grievances. Answers raise flags "
                       "to follow up; they are not scored.",
        "questions": [
            _dd("policy", "Do you have a written policy that commits your company to respect human rights and the "
                          "environment?", "yes", "LkSG § 6(4); CSDDD Article 10"),
            _dd("supplier_expectations", "Do you pass these expectations on to your own suppliers and check that "
                                         "they meet them?", "yes", "LkSG § 6(4); CSDDD Article 10"),
            _dd("grievance", "Can workers and people affected by your operations raise concerns through a grievance "
                             "channel, without fear of reprisal?", "yes", "LkSG § 8; CSDDD Article 14"),
            _dd("age_checks", "Do you verify the age of every worker at the sites that supply us, including agency "
                              "and subcontracted workers?", "yes", "LkSG § 2(2) no. 1-2; CSDDD Annex Part I, 9-10"),
            _dd("forced_labour", "Does any worker pay recruitment fees, hand over identity documents, or have their "
                                 "freedom to leave restricted?", "no", "LkSG § 2(2) no. 3-4; CSDDD Annex Part I, 11-12"),
            _dd("safety_system", "Do the sites that supply us run an occupational safety and health system, with "
                                 "risk assessments and training?", "yes", "LkSG § 2(2) no. 5; CSDDD Annex Part I, 6"),
            _dd("working_hours", "Do working hours, including overtime, stay within the limits of local law?", "yes",
                "LkSG § 2(2) no. 5(c); CSDDD Annex Part I, 6"),
            _dd("wages", "Is every worker paid at least the legal minimum wage, in full and on time?", "yes",
                "LkSG § 2(2) no. 8; CSDDD Annex Part I, 6"),
            _dd("association", "Are workers free to form or join a trade union and to bargain collectively?", "yes",
                "LkSG § 2(2) no. 6; CSDDD Annex Part I, 13"),
            _dd("equal_treatment", "Do you have a non-discrimination policy that includes equal pay for work of equal "
                                   "value?", "yes", "LkSG § 2(2) no. 7; CSDDD Annex Part I, 14"),
            _dd("environment_permits", "Do the sites that supply us hold their environmental permits and monitor "
                                       "discharges to water, air and soil?", "yes",
                "LkSG § 2(2) no. 9; CSDDD Annex Part I, 15"),
            _dd("mercury_pops", "Do you use mercury, mercury compounds or persistent organic pollutants (Stockholm "
                                "Convention, Annex A) to make the products you supply to us?", "no",
                "LkSG § 2(3) no. 1-4; CSDDD Annex Part II, 3-6"),
            _dd("waste_contractors", "Is your hazardous waste handled only by licensed contractors?", "yes",
                "LkSG § 2(3) no. 5; CSDDD Annex Part II, 7"),
            _dd("waste_export", "Do you export hazardous waste to another country?", "no",
                "LkSG § 2(3) no. 6-8; CSDDD Annex Part II, 10-12", weight=2),
            _dd("land_security", "In the last five years, did any of your sites involve resettling people or "
                                 "acquiring land they used, or use armed security?", "no",
                "LkSG § 2(2) no. 10-11; CSDDD Annex Part I, 1-2 and 16", weight=2),
            _dd("breaches", "In the last 36 months, have authorities, auditors or workers found a breach in any of "
                            "these areas at your company?", "no", "LkSG §§ 5, 7; CSDDD Articles 8, 11"),
            _q("breaches_detail", "If yes, what was found and what has been done since?", "text"),
            _q("certifications", "Audits or certifications that cover these areas (for example SA8000, SMETA, "
                                 "ISO 45001, ISO 14001), with their dates", "text"),
            _q("subtier", "Your suppliers for the products you supply to us", "subtier",
               help="Name, country and what they supply; used to see where risks may sit deeper in the chain."),
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
        if q.get("flag_only"):
            if answers[q["id"]] != q["good"]:
                flags.append({"id": q["id"], "text": q["text"], "answer": answers[q["id"]], "weight": weight})
            continue
        total += weight
        if answers[q["id"]] == q["good"]:
            good += weight
        else:
            flags.append({"id": q["id"], "text": q["text"], "answer": answers[q["id"]], "weight": weight})
    flags.sort(key=lambda f: -f["weight"])
    return (round(100 * good / total) if total else None), flags
