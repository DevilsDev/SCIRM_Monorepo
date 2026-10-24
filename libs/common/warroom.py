"""War room helpers: the spend exposure of an incident's suppliers.

Spend is kept per currency, as SAP reports it (supplier.spend_12m = {currency: amount}).
Totals are per currency and never added across currencies: there is no exchange rate in
SCIRM, and a sum in mixed currencies would be wrong."""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List


def exposure(suppliers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """{"by_currency": {currency: total as a string}, "without_spend": n} for 12-month spend."""
    totals: Dict[str, Decimal] = {}
    without = 0
    for supplier in suppliers:
        spend = supplier.get("spend_12m") or {}
        if not isinstance(spend, dict) or not spend:
            without += 1
            continue
        for currency, amount in spend.items():
            try:
                totals[currency] = totals.get(currency, Decimal("0")) + Decimal(str(amount))
            except (InvalidOperation, TypeError):
                continue
    return {"by_currency": {c: str(totals[c]) for c in sorted(totals)}, "without_spend": without}
