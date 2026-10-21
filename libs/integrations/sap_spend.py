"""
Purchase-order spend from an SAP export, to rank suppliers by what is bought from them.

The customer exports purchase-order items with their header fields (EKPO joined with
EKKO, or an ME2N/ME2L list exported to a file) and uploads it; or, on S/4HANA, the
orders are read over OData from the tenant's connection (libs/integrations/sap_odata.py)
as the same lines.

    parse_po_extract(text, column_map, decimal)  -> lines, warnings
    summarize(lines)                             -> spend per SAP supplier number
    plan_spend(summary, existing)                -> updates for this tenant's suppliers

Rules:
- Spend is the sum of item net values (NETWR) over the 12 months up to the latest order
  date in the file. Items marked for deletion (LOEKZ) are excluded.
- Currencies are never converted or added together: totals are kept per currency (WAERS).
  Ranking uses the main currency: the one on the most order lines (ties: alphabetical).
  Amounts in different currencies are never compared, so ¥ or ₹ totals cannot win on size
  alone. Only suppliers with spend in the main currency are ranked; spend in other
  currencies is still reported, unranked.
- Each upload replaces earlier spend: suppliers imported from SAP with no orders in the
  period get zero spend for it. Spend on SAP numbers that are not imported suppliers is
  reported, not dropped silently.
"""

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from libs.integrations.sap_import import _flag, _rows, normalize_number

MAX_LINES = 500_000
PERIOD_DAYS = 365

COLUMNS = {
    "number": ("lifnr",),          # supplier
    "date": ("bedat",),            # purchasing document date
    "amount": ("netwr",),          # item net order value
    "currency": ("waers",),
    "document": ("ebeln",),
    "plant": ("werks",),
    "deletion_flag": ("loekz",),
}
REQUIRED = ("number", "date", "amount", "currency")


def parse_date(value: str) -> Optional[date]:
    """SAP user date formats: DD.MM.YYYY, MM/DD/YYYY, MM-DD-YYYY, and year-first with any
    separator; also YYYYMMDD. Each has a fixed field order, so no date is guessed."""
    v = (value or "").strip()
    try:
        if re.fullmatch(r"\d{8}", v):
            return date(int(v[:4]), int(v[4:6]), int(v[6:]))
        m = re.fullmatch(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", v)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.fullmatch(r"(\d{1,2})([./-])(\d{1,2})\2(\d{4})", v)
        if m:
            first, sep, second, year = int(m[1]), m[2], int(m[3]), int(m[4])
            return date(year, second, first) if sep == "." else date(year, first, second)
    except ValueError:
        return None
    return None


def parse_amount(value: str, decimal: Optional[str] = None) -> Optional[Decimal]:
    """'1.234,56', '1,234.56', '1 234,56', and SAP's trailing minus ('123,45-')."""
    v = (value or "").strip().replace(" ", "").replace(" ", "")
    if not v:
        return None
    negative = v.endswith("-") or v.startswith("-")
    v = v.strip("-")
    if decimal not in (".", ","):
        last_dot, last_comma = v.rfind("."), v.rfind(",")
        if last_dot >= 0 and last_comma >= 0:
            decimal = "." if last_dot > last_comma else ","
        elif last_dot >= 0 or last_comma >= 0:
            sep = "." if last_dot >= 0 else ","
            tail = v.rsplit(sep, 1)[1]
            if v.count(sep) > 1:
                decimal = "," if sep == "." else "."  # repeated: thousands ("1.234.567")
            else:
                # A single separator followed by three digits ("1,234") reads two ways.
                decimal = "?" if len(tail) == 3 else sep
        else:
            decimal = "."
    if decimal == "?":
        return None  # ambiguous, e.g. "1,234"; the caller warns and the user sets `decimal`
    thousands = "," if decimal == "." else "."
    v = v.replace(thousands, "").replace(decimal, ".")
    try:
        amount = Decimal(v)
    except InvalidOperation:
        return None
    return -amount if negative else amount


def parse_po_extract(text: str, column_map: Optional[Dict[str, str]] = None,
                     decimal: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    text = (text or "").lstrip("﻿")
    rows = [r for r in _rows(text) if any(c.strip() for c in r)] if text.strip() else []
    if not rows:
        return [], ["The file is empty."]
    header = [h.strip().lower() for h in rows[0]]
    mapped = {k: v.strip().lower() for k, v in (column_map or {}).items() if k in COLUMNS and v}
    index = {f: next((i for i, h in enumerate(header) if h in ((mapped[f],) if f in mapped else names)), None)
             for f, names in COLUMNS.items()}
    missing = [f for f in REQUIRED if index[f] is None]
    if missing:
        return [], [f"Columns not found: {', '.join(COLUMNS[f][0].upper() for f in missing)}. "
                    f"Map them to your file's headers (found: {', '.join(rows[0])})."]

    def cell(row, field):
        i = index[field]
        return row[i].strip() if i is not None and i < len(row) else ""

    lines, warnings, problems = [], [], defaultdict(int)
    ambiguous = 0
    for line_no, row in enumerate(rows[1:], start=2):
        number = normalize_number(cell(row, "number"))
        if not number:
            problems["no supplier number"] += 1
            continue
        when = parse_date(cell(row, "date"))
        if when is None:
            problems["unreadable date"] += 1
            continue
        raw_amount = cell(row, "amount")
        amount = parse_amount(raw_amount, decimal)
        if amount is None:
            if raw_amount and decimal is None and re.search(r"[.,]\d{3}$", raw_amount):
                ambiguous += 1
            else:
                problems["unreadable amount"] += 1
            continue
        currency = cell(row, "currency").upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            problems["no currency"] += 1
            continue
        lines.append({"number": number, "date": when, "amount": amount, "currency": currency,
                      "document": cell(row, "document") or None, "plant": cell(row, "plant") or None,
                      "deleted": _flag(cell(row, "deletion_flag")), "line": line_no})
        if len(lines) >= MAX_LINES:
            warnings.append(f"Only the first {MAX_LINES} lines were read.")
            break
    for what, n in sorted(problems.items()):
        warnings.append(f"{n} line(s) skipped: {what}.")
    if ambiguous:
        warnings.append(f"{ambiguous} amount(s) such as '1,234' could be read two ways and were skipped. "
                        "Choose the decimal separator your export uses.")
    return lines, warnings


def summarize(lines: List[Dict[str, Any]], period_days: int = PERIOD_DAYS, end: Optional[date] = None) -> Dict[str, Any]:
    """Spend per supplier over `period_days` ending at `end`. A file covers whatever its
    export covered, so by default the period ends at its latest order. Orders read from
    SAP over OData were fetched for a period ending today, which is passed as `end`, so
    the period matches what was fetched even when the latest order is months old."""
    kept = [l for l in lines if not l["deleted"]]
    if not kept:
        return {"period": None, "suppliers": {}, "currencies": {}, "main_currency": None, "currency_lines": {},
                "lines": {"read": len(lines), "deleted": len(lines), "before_period": 0, "counted": 0}}
    end = end or max(l["date"] for l in kept)
    start = end - timedelta(days=period_days - 1)
    in_period = [l for l in kept if start <= l["date"] <= end]
    suppliers: Dict[str, Dict[str, Any]] = {}
    currencies: Dict[str, Decimal] = defaultdict(Decimal)
    line_counts: Dict[str, int] = defaultdict(int)
    for l in in_period:
        line_counts[l["currency"]] += 1
        s = suppliers.setdefault(l["number"], {"spend": defaultdict(Decimal), "documents": set(), "lines": 0,
                                               "plants": set(), "last_order": l["date"]})
        s["spend"][l["currency"]] += l["amount"]
        currencies[l["currency"]] += l["amount"]
        s["lines"] += 1
        s["last_order"] = max(s["last_order"], l["date"])
        if l["document"]:
            s["documents"].add(l["document"])
        if l["plant"]:
            s["plants"].add(l["plant"])
    main = min(line_counts, key=lambda c: (-line_counts[c], c)) if line_counts else None
    out = {}
    for number, s in suppliers.items():
        out[number] = {"spend": {c: str(v.quantize(Decimal("0.01"))) for c, v in sorted(s["spend"].items())},
                       "orders": len(s["documents"]) or None, "lines": s["lines"],
                       "plants": sorted(s["plants"]), "last_order": s["last_order"].isoformat()}
    return {"period": {"from": start.isoformat(), "to": end.isoformat()}, "suppliers": out,
            "currencies": {c: str(v.quantize(Decimal("0.01"))) for c, v in sorted(currencies.items())},
            "main_currency": main, "currency_lines": dict(sorted(line_counts.items())),
            "lines": {"read": len(lines), "deleted": len(lines) - len(kept),
                      "before_period": len(kept) - len(in_period), "counted": len(in_period)}}


def plan_spend(summary: Dict[str, Any], existing: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Updates that set each SAP supplier's spend for the period (zero when it had no
    orders), the ranking in the main currency, and spend on unknown SAP numbers. A
    supplier with no spend in the main currency gets no rank or share, whatever it spent
    in other currencies; it is listed after the ranked suppliers."""
    period, main = summary["period"], summary["main_currency"]
    by_number = {str(s["sap_supplier_number"]): s for s in existing if s.get("sap_supplier_number")}
    found = summary["suppliers"]
    main_total = Decimal(summary["currencies"].get(main, "0")) if main else Decimal("0")
    updates, ranked = [], []
    for number, supplier in by_number.items():
        s = found.get(number)
        spend = s["spend"] if s else {}
        in_main = bool(main) and main in spend
        main_spend = Decimal(spend[main]) if in_main else Decimal("0")
        share = float(main_spend / main_total) if in_main and main_total > 0 else None
        fields = {"spend_12m": spend, "spend_period": period, "spend_main_currency": main,
                  "spend_share": round(share, 4) if share is not None else None,
                  "spend_orders": s["orders"] if s else 0, "spend_last_order": s["last_order"] if s else None,
                  "spend_plants": s["plants"] if s else []}
        updates.append({"supplier_id": str(supplier["id"]), "number": number, "name": supplier.get("name"),
                        "fields": fields})
        fields["spend_rank"] = None
        # Sort key: ranked first by main-currency spend, then other-currency-only, then no spend.
        ranked.append(((in_main, bool(spend), main_spend), number, supplier.get("name"), spend, share))
    ranked.sort(key=lambda r: r[0], reverse=True)
    fields_by_number = {u["number"]: u["fields"] for u in updates}
    if main_total > 0:
        for rank, (_, number, _, _, _) in enumerate((r for r in ranked if r[0][0]), start=1):
            fields_by_number[number]["spend_rank"] = rank
    unknown = sorted(((n, s["spend"]) for n, s in found.items() if n not in by_number),
                     key=lambda x: Decimal(x[1].get(main, "0")) if main else 0, reverse=True)
    return {"period": period, "main_currency": main, "currencies": summary["currencies"],
            "currency_lines": summary.get("currency_lines", {}), "lines": summary["lines"], "updates": updates,
            "top": [{"rank": fields_by_number[n]["spend_rank"], "number": n, "name": name, "spend": sp,
                     "share": round(sh, 4) if sh is not None else None}
                    for _, n, name, sp, sh in ranked[:20]],
            "unknown_suppliers": [{"number": n, "spend": sp} for n, sp in unknown[:200]],
            "unknown_count": len(unknown),
            "with_spend": sum(1 for n in by_number if n in found)}
