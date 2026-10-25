"""Spend at risk when suppliers are out, and what would reduce it. Deterministic code only.

The measure is **purchase spend at risk**, not revenue: SCIRM has each supplier's 12-month
purchase spend from SAP (per currency), not revenue or bills of materials.

For a scenario "these suppliers are out for N weeks":
- purchase flow interrupted = 12-month spend x N / 52, per currency;
- the supplier's safety stock covers the first weeks. Its weeks come from the supplier's own
  answer in a supplier assessment (supplier-provided). Without an answer, coverage is 0 weeks,
  and the result says so: missing data is never filled in with a guess;
- spend at risk = 12-month spend x (N - covered weeks) / 52, never below 0.

Amounts are never converted or added across currencies. Suppliers and mitigations are ranked
by the organization's main currency (the one on most order lines: the Phase 1 rule); ones
without spend in it are listed after, unranked.

Resilience planner: for each supplier in the scenario, the reduction in spend at risk from
- raising safety stock to T weeks: spend x (uncovered now - uncovered with T) / 52;
- qualifying a second source for a share s of the volume: s x spend at risk.
Each is computed on its own against the scenario, with the assumptions (T, s) shown.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

WEEKS_PER_YEAR = Decimal(52)
CENT = Decimal("0.01")


def _money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _spend(supplier: Dict[str, Any]) -> Dict[str, Decimal]:
    out: Dict[str, Decimal] = {}
    for currency, amount in (supplier.get("spend_12m") or {}).items():
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, TypeError):
            continue
        if value > 0:
            out[str(currency)] = value
    return out


def _scale(spend: Dict[str, Decimal], weeks: Decimal) -> Dict[str, Decimal]:
    return {c: v * weeks / WEEKS_PER_YEAR for c, v in spend.items()}


def _add(totals: Dict[str, Decimal], amounts: Dict[str, Decimal]) -> None:
    for c, v in amounts.items():
        totals[c] = totals.get(c, Decimal(0)) + v


def _strings(amounts: Dict[str, Decimal]) -> Dict[str, str]:
    return {c: _money(amounts[c]) for c in sorted(amounts)}


def main_currency(suppliers: List[Dict[str, Any]]) -> Optional[str]:
    """The organization's main currency as the SAP spend import set it (most order lines)."""
    found = [s.get("spend_main_currency") for s in suppliers if s.get("spend_main_currency")]
    return max(set(found), key=found.count) if found else None


def run(suppliers: List[Dict[str, Any]], duration_weeks: int, coverage: Dict[str, Dict[str, Any]],
        currency: Optional[str], stock_target_weeks: Optional[int] = None,
        second_source_share: Optional[float] = None) -> Dict[str, Any]:
    """`coverage`: supplier id -> {"weeks": float, "source": str, "single_source": bool|None}
    from assessments (absent = unknown). Returns the scenario result and the plan."""
    n = Decimal(duration_weeks)
    target = Decimal(stock_target_weeks if stock_target_weeks is not None else duration_weeks)
    share = Decimal(str(second_source_share if second_source_share is not None else 0.5))
    rows, interrupted_total, at_risk_total, unknown = [], {}, {}, 0
    mitigations: List[Dict[str, Any]] = []
    for s in suppliers:
        spend = _spend(s)
        known = coverage.get(str(s.get("id")))
        weeks = Decimal(str(known["weeks"])) if known and known.get("weeks") is not None else Decimal(0)
        if not known or known.get("weeks") is None:
            unknown += 1
        covered = min(weeks, n)
        uncovered = n - covered
        interrupted, at_risk = _scale(spend, n), _scale(spend, uncovered)
        _add(interrupted_total, interrupted)
        _add(at_risk_total, at_risk)
        rows.append({
            "supplier_id": str(s.get("id")), "name": s.get("name"), "country_code": s.get("country_code"),
            "spend_12m": _strings(spend), "coverage_weeks": float(weeks) if known and known.get("weeks") is not None else None,
            "coverage_source": known["source"] if known and known.get("weeks") is not None
            else "unknown: no safety-stock answer from the supplier, counted as 0 weeks",
            "single_source": (known or {}).get("single_source"),
            "uncovered_weeks": float(uncovered), "interrupted": _strings(interrupted), "at_risk": _strings(at_risk),
            "_rank": at_risk.get(currency, Decimal(-1)) if currency else Decimal(-1)})
        if not spend or uncovered <= 0:
            continue
        stock_uncovered = n - min(max(weeks, target), n)
        stock_cut = _scale(spend, uncovered - stock_uncovered)
        if any(v > 0 for v in stock_cut.values()):
            mitigations.append({"supplier_id": str(s.get("id")), "name": s.get("name"), "kind": "safety_stock",
                                "description": f"Raise safety stock from {float(weeks):g} to {float(target):g} weeks",
                                "reduction": _strings(stock_cut), "_rank": stock_cut.get(currency, Decimal(-1))})
        source_cut = {c: v * share for c, v in at_risk.items()}
        reason = " (the supplier reports a single source or site)" if (known or {}).get("single_source") else ""
        mitigations.append({"supplier_id": str(s.get("id")), "name": s.get("name"), "kind": "second_source",
                            "description": f"Qualify a second source for {float(share) * 100:g}% of the volume{reason}",
                            "reduction": _strings(source_cut), "_rank": source_cut.get(currency, Decimal(-1))})

    def ranked(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        main = [i for i in items if i["_rank"] >= 0]
        other = [i for i in items if i["_rank"] < 0]
        main.sort(key=lambda i: (-i["_rank"], i["name"] or ""))
        other.sort(key=lambda i: i["name"] or "")
        strip = lambda i: {k: v for k, v in i.items() if k != "_rank"}  # noqa: E731
        return {"ranked": [strip(i) for i in main], "other_currencies": [strip(i) for i in other]}

    return {
        "duration_weeks": duration_weeks, "main_currency": currency, "supplier_count": len(rows),
        "suppliers_without_coverage_data": unknown,
        "interrupted": _strings(interrupted_total), "at_risk": _strings(at_risk_total),
        "suppliers": ranked(rows),
        "plan": ranked(mitigations),
        "assumptions": [
            "Spend is 12-month purchase spend from the SAP spend import, per currency; it is not revenue.",
            f"The suppliers are out for {duration_weeks} weeks; purchase flow interrupted = spend x {duration_weeks}/52.",
            "Safety stock covers the first weeks, as the supplier stated it in an assessment (supplier-provided, "
            "not verified); without an answer it counts as 0 weeks.",
            f"Raising safety stock is evaluated to {float(target):g} weeks; a second source is assumed to take "
            f"{float(share) * 100:g}% of the volume. Each mitigation is computed alone against the scenario.",
            "Amounts are never converted or added across currencies; ranking is by the main currency"
            + (f" ({currency})." if currency else " (none: no SAP spend import yet)."),
        ],
    }
