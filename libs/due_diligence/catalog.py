"""Human rights and environmental due diligence: the risk areas, the measures and the review
cycle, taken from the law as it stands (read 25 October 2026):

- LkSG (Lieferkettensorgfaltspflichtengesetz, in force, unamended): the prohibitions in
  section 2(2) no. 1-12 (human rights) and 2(3) no. 1-8 (environment); the risk analysis
  once a year and when the risk situation changes (section 5(4)); documentation kept for
  seven years (section 10(1)).
- CSDDD (Directive (EU) 2024/1760 as amended by Directive (EU) 2026/470): the Annex, Part I
  (human rights, points 1-16) and Part II (environment, points 1-16), which the amendment
  left unchanged; monitoring at least every five years and after a significant change
  (Article 15 as replaced); the last-resort steps of Article 10(6) as replaced.

People rate every risk. Nothing here scores a supplier, a country or a sector.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

# key: (label, LkSG reference, CSDDD Annex reference, group)
AREAS: Dict[str, Dict[str, str]] = {}


def _area(key: str, label: str, lksg: str, csddd: str, group: str) -> None:
    AREAS[key] = {"key": key, "label": label, "lksg": lksg, "csddd": csddd, "group": group}


_area("child_labour", "Child labour below the minimum age", "§ 2(2) no. 1", "Annex Part I, 9", "human_rights")
_area("worst_forms_child_labour", "Worst forms of child labour (under 18)", "§ 2(2) no. 2", "Annex Part I, 10",
      "human_rights")
_area("forced_labour", "Forced or compulsory labour", "§ 2(2) no. 3", "Annex Part I, 11", "human_rights")
_area("slavery", "Slavery, servitude and oppression at the workplace", "§ 2(2) no. 4", "Annex Part I, 12",
      "human_rights")
_area("occupational_safety", "Occupational safety and health", "§ 2(2) no. 5", "Annex Part I, 6", "human_rights")
_area("freedom_of_association", "Freedom of association and collective bargaining", "§ 2(2) no. 6",
      "Annex Part I, 13", "human_rights")
_area("discrimination", "Unequal treatment in employment, including unequal pay", "§ 2(2) no. 7",
      "Annex Part I, 14", "human_rights")
_area("fair_wage", "Withholding an adequate wage", "§ 2(2) no. 8", "Annex Part I, 6", "human_rights")
_area("environmental_harm_to_people", "Soil, water or air pollution, noise or excessive water use that harms people",
      "§ 2(2) no. 9", "Annex Part I, 15", "human_rights")
_area("land_rights", "Unlawful eviction or taking of land, forests or waters", "§ 2(2) no. 10", "Annex Part I, 16",
      "human_rights")
_area("security_forces", "Abuses by private or public security forces", "§ 2(2) no. 11", "Annex Part I, 1 and 2",
      "human_rights")
_area("workers_housing", "Restricting workers' access to adequate housing, food, water and sanitation", "",
      "Annex Part I, 7", "human_rights")
_area("other_human_rights", "Other human rights (life, liberty, privacy, freedom of thought, children's health)",
      "§ 2(2) no. 12", "Annex Part I, 1-5 and 8", "human_rights")
_area("mercury_products", "Manufacturing mercury-added products", "§ 2(3) no. 1", "Annex Part II, 3", "environment")
_area("mercury_processes", "Using mercury in manufacturing processes", "§ 2(3) no. 2", "Annex Part II, 4",
      "environment")
_area("mercury_waste", "Unlawful treatment of mercury waste", "§ 2(3) no. 3", "Annex Part II, 5", "environment")
_area("persistent_organic_pollutants", "Producing or using persistent organic pollutants (Stockholm Annex A)",
      "§ 2(3) no. 4", "Annex Part II, 6", "environment")
_area("pops_waste", "Unsound handling, storage or disposal of waste (Stockholm Convention)", "§ 2(3) no. 5",
      "Annex Part II, 7", "environment")
_area("hazardous_waste_export", "Prohibited exports of hazardous or other waste (Basel Convention)", "§ 2(3) no. 6",
      "Annex Part II, 10", "environment")
_area("hazardous_waste_annex_vii", "Exports of hazardous waste from Basel Annex VII countries", "§ 2(3) no. 7",
      "Annex Part II, 11", "environment")
_area("hazardous_waste_import", "Imports of hazardous or other waste from a non-party (Basel Convention)",
      "§ 2(3) no. 8", "Annex Part II, 12", "environment")
_area("hazardous_chemicals_trade", "Trade in restricted chemicals or ozone-depleting substances", "",
      "Annex Part II, 8 and 9", "environment")
_area("biodiversity", "Biodiversity, endangered species, World Heritage sites and wetlands", "",
      "Annex Part II, 1, 2, 13 and 14", "environment")
_area("marine_pollution", "Pollution from ships and of the marine environment", "", "Annex Part II, 15 and 16",
      "environment")

SOURCES = ("scoping", "in_depth", "supplier_reported", "incident", "public_record", "notification")
SOURCE_LABEL = {
    "scoping": "Scoping (reasonably available information)",
    "in_depth": "In-depth assessment",
    "supplier_reported": "Supplier questionnaire",
    "incident": "War-room incident",
    "public_record": "Public record",
    "notification": "Notification or complaint received",
}

# 1-4, set by a person. Severity is the scale, scope and irremediability of the impact.
LIKELIHOOD = {1: "Unlikely", 2: "Possible", 3: "Likely", 4: "Very likely or occurring"}
SEVERITY = {1: "Low", 2: "Moderate", 3: "High", 4: "Severe"}
RISK_STATUSES = ("open", "mitigated", "closed")

MEASURE_KINDS = {
    "code_of_conduct": "Supplier code of conduct or contractual assurance",
    "training": "Training or capacity building",
    "audit": "Audit or on-site check",
    "corrective_action_plan": "Corrective action plan with the supplier",
    "industry_initiative": "Industry or multi-stakeholder initiative",
    "purchasing_practice": "Change to our own purchasing practices",
    "remediation": "Remediation for the people affected",
    "enhanced_prevention_plan": "Enhanced prevention action plan (last resort)",
    "refrain_new_business": "No new or extended business while unresolved (last resort)",
    "suspend": "Suspend the relationship for the activities concerned (last resort)",
    "terminate": "End the business relationship (last resort)",
    "other": "Other",
}
LAST_RESORT = ("enhanced_prevention_plan", "refrain_new_business", "suspend", "terminate")
MEASURE_STATUSES = ("planned", "in_progress", "done", "cancelled")
EFFECTIVENESS = ("not_reviewed", "effective", "partly_effective", "not_effective")

DEFAULT_REVIEW_MONTHS = 12  # LkSG section 5(4): once a year
MAX_REVIEW_MONTHS = 60      # CSDDD Article 15: at least every five years


def priority_key(risk: Dict[str, Any]) -> tuple:
    """Order risks by severity first, then likelihood (CSDDD Article 9; LkSG section 3(2)).
    Closed risks go last. No combined number is computed."""
    return (risk.get("status") == "closed", -(risk.get("severity") or 0), -(risk.get("likelihood") or 0))


def _months_after(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31,
            30, 31][month - 1]
    return moment.replace(year=year, month=month, day=min(moment.day, days))


def review_status(last_review: Optional[datetime], interval_months: int, changes: Iterable[Dict[str, Any]],
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Where a supplier's risk analysis stands.

    `changes` are dated facts SCIRM already holds about the supplier (an incident opened, a
    questionnaire submitted); one after the last review suggests reviewing again, as a
    significant change would. Only the dates are compared.
    """
    now = now or datetime.now(timezone.utc)
    if last_review is None:
        return {"state": "not_analysed", "last_review": None, "next_review": None, "reasons": []}
    due = _months_after(last_review, interval_months)
    reasons: List[str] = [c["text"] for c in changes if c["at"] > last_review]
    state = "due" if now >= due else ("suggested" if reasons else "current")
    return {"state": state, "last_review": last_review.isoformat(), "next_review": due.isoformat(),
            "reasons": reasons}
