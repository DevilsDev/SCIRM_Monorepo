"""
Supplier master import from an SAP extract (table LFA1: the vendor master in SAP ECC
and S/4HANA).

The customer exports LFA1 from their own system (for example with transaction SE16N)
and uploads the file. Nothing connects to their SAP, and no SAP credentials are stored.

    parse_extract(text, column_map)          -> rows, warnings
    plan_import(rows, existing, decisions)   -> what an import would change (the preview)

Applying the plan is the caller's job (services/coordinator). Rules:
- The key is the SAP supplier number, with leading zeros removed from numeric ones:
  0000100123 and 100123 are the same supplier.
- New suppliers get supplier_code "SAP-<number>". Existing suppliers keep their code and
  are recognised by metadata["sap_supplier_number"].
- A new number whose name matches a supplier entered by hand is not created or merged
  automatically: a person decides to link it to that supplier or to create a new one.
- Rows marked for deletion are not imported. Blocked suppliers are imported as inactive.
- Nothing is deleted. Suppliers missing from the file are reported; they are only
  deactivated on request, and not when the file is much smaller than the last import.
- Aliases are only added, never removed, so names entered by hand survive a re-import.
"""

import csv
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from libs.intel import matching
from libs.intel.sources import IMPORT_ALERT_COUNTRIES

MAX_ROWS = 20000
SAP_NAME_LENGTH = 35  # LFA1-NAME1 is 35 characters; a full field may continue in NAME2.
MIN_RATIO = 0.5       # deactivating missing suppliers needs at least half of the last import

# Field -> LFA1 technical column names accepted for it.
COLUMNS = {
    "number": ("lifnr",),
    "name1": ("name1",),
    "name2": ("name2",),
    "name3": ("name3",),
    "name4": ("name4",),
    "country": ("land1",),
    "city": ("ort01",),
    "posting_block": ("sperr",),
    "purchasing_block": ("sperm",),
    "deletion_flag": ("loevm",),
    "vat_number": ("stceg",),
}
REQUIRED = ("number", "name1")

# Legal-form words: a second name line is used as an alias only if it reads as a company
# name. Department, "c/o" and address lines would cause wrong-supplier matches.
LEGAL_FORMS = {
    "ag", "ab", "as", "a/s", "bv", "b.v.", "co", "co.", "corp", "corp.", "corporation", "gmbh", "inc", "inc.",
    "kg", "kgaa", "kk", "limited", "llc", "llp", "lp", "ltd", "ltd.", "nv", "n.v.", "oy", "oyj", "plc", "pte",
    "pty", "pvt", "s.a.", "s.a.s.", "s.p.a.", "s.r.l.", "sa", "sarl", "sas", "se", "spa", "srl", "ulc",
}
NOT_A_NAME = re.compile(r"^\s*(c/o|attn|attention|z\.?\s?hd|dept|department|abt\.?|abteilung|p\.?o\.? box|\d)", re.I)


def normalize_number(value: str) -> str:
    value = (value or "").strip().upper()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def _country(value: str) -> Optional[str]:
    value = (value or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", value):
        return value.upper()
    return IMPORT_ALERT_COUNTRIES.get(value.lower()) if value else None


def _is_company_name(text: str) -> bool:
    if not text or NOT_A_NAME.match(text):
        return False
    words = {w.strip(",()").lower() for w in text.split()}
    return bool(words & LEGAL_FORMS)


def _flag(value: str) -> bool:
    return (value or "").strip().upper() not in ("", "0", "N", "FALSE")


def _rows(text: str) -> List[List[str]]:
    sample = text[:4096]
    if "\t" in sample:
        dialect = csv.excel_tab
    else:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;|")
        except csv.Error:
            dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def parse_extract(text: str, column_map: Optional[Dict[str, str]] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Rows of an LFA1 extract. `column_map` maps a field (see COLUMNS) to the file's header,
    for exports whose headers are labels rather than technical names."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        return [], ["The file is empty."]
    rows = [r for r in _rows(text) if any(c.strip() for c in r)]
    if not rows:
        return [], ["The file is empty."]
    header = [h.strip().lower() for h in rows[0]]
    mapped = {k: v.strip().lower() for k, v in (column_map or {}).items() if k in COLUMNS and v}
    index = {}
    for field, names in COLUMNS.items():
        wanted = (mapped[field],) if field in mapped else names
        index[field] = next((i for i, h in enumerate(header) if h in wanted), None)
    missing = [f for f in REQUIRED if index[f] is None]
    if missing:
        return [], [f"Columns not found: {', '.join(COLUMNS[f][0].upper() for f in missing)}. "
                    f"Map them to your file's headers (found: {', '.join(rows[0])})."]

    def cell(row, field):
        i = index[field]
        return row[i].strip() if i is not None and i < len(row) else ""

    warnings, out, seen = [], [], {}
    for line, row in enumerate(rows[1:], start=2):
        number = normalize_number(cell(row, "number"))
        name1 = cell(row, "name1")
        if not number or not name1:
            warnings.append(f"Row {line}: no supplier number or name; skipped.")
            continue
        if number in seen:
            warnings.append(f"Row {line}: supplier {number} already appears on row {seen[number]}; skipped.")
            continue
        seen[number] = line
        name, extra = name1, [cell(row, f) for f in ("name2", "name3", "name4")]
        if len(name1) >= SAP_NAME_LENGTH and extra[0]:
            name, extra = f"{name1} {extra[0]}", extra[1:]
        aliases = [e for e in extra if _is_company_name(e) and matching.normalize(e) != matching.normalize(name)]
        country_raw = cell(row, "country")
        country = _country(country_raw)
        if country_raw and not country:
            warnings.append(f"Row {line}: country '{country_raw}' not recognised; disaster exposure skipped for {name}.")
        out.append({
            "number": number, "name": name[:255], "country_code": country, "city": cell(row, "city") or None,
            "aliases": aliases, "vat_number": cell(row, "vat_number") or None,
            "blocked": _flag(cell(row, "posting_block")) or _flag(cell(row, "purchasing_block")),
            "deletion_flag": _flag(cell(row, "deletion_flag")), "line": line,
        })
        if len(out) >= MAX_ROWS:
            warnings.append(f"Only the first {MAX_ROWS} suppliers were read.")
            break
    return out, warnings


def _target(row: Dict[str, Any]) -> Dict[str, Any]:
    """The supplier fields SAP owns."""
    return {"name": row["name"], "country_code": row["country_code"], "is_active": not row["blocked"],
            "sap_supplier_number": row["number"], "sap_city": row["city"], "sap_vat_number": row["vat_number"],
            "sap_blocked": row["blocked"]}


def plan_import(rows: List[Dict[str, Any]], existing: List[Dict[str, Any]],
                decisions: Optional[Dict[str, str]] = None, deactivate_missing: bool = False) -> Dict[str, Any]:
    """What importing `rows` into a tenant with suppliers `existing` would change.

    `decisions` settles possible duplicates: {sap number: "create" | "link:<supplier id>"}.
    Each action carries the supplier fields to write, so applying needs no further logic.
    """
    decisions = decisions or {}
    by_number = {str(s["sap_supplier_number"]): s for s in existing if s.get("sap_supplier_number")}
    by_id = {str(s["id"]): s for s in existing}
    manual_by_name: Dict[str, Dict[str, Any]] = {}
    for s in existing:
        if not s.get("sap_supplier_number") and s.get("name"):
            manual_by_name.setdefault(matching.normalize(s["name"]), s)

    actions: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    linked = set()

    def update_action(row, current, kind="update"):
        target = _target(row)
        # SAP sets "active" only when its block changes, or when a supplier this import
        # deactivated as missing is back; a person's own deactivation otherwise stands.
        if kind != "link" and current.get("sap_blocked") == row["blocked"] and not current.get("sap_missing"):
            target.pop("is_active")
        if current.get("sap_missing"):
            target["sap_missing"] = False
        aliases = list(dict.fromkeys((current.get("aliases") or []) + row["aliases"]))
        changes = {k: v for k, v in target.items() if current.get(k) != v}
        if aliases != list(current.get("aliases") or []):
            changes["aliases"] = aliases
        if kind == "link" or changes:
            actions.append({"action": kind, "number": row["number"], "name": row["name"],
                            "supplier_id": str(current["id"]), "fields": changes or target,
                            "changed": sorted(changes)})
        else:
            actions.append({"action": "unchanged", "number": row["number"], "name": row["name"],
                            "supplier_id": str(current["id"])})

    for row in rows:
        current = by_number.get(row["number"])
        if row["deletion_flag"]:
            if current and current.get("is_active", True):
                actions.append({"action": "deactivate", "number": row["number"], "name": row["name"],
                                "supplier_id": str(current["id"]), "fields": {"is_active": False},
                                "reason": "marked for deletion in SAP"})
            else:
                actions.append({"action": "skip", "number": row["number"], "name": row["name"],
                                "reason": "marked for deletion in SAP"})
            continue
        if current:
            update_action(row, current)
            continue
        decision = decisions.get(row["number"], "")
        clash = manual_by_name.get(matching.normalize(row["name"]))
        if decision.startswith("link:"):
            target_supplier = by_id.get(decision[5:])
            if target_supplier is None or target_supplier.get("sap_supplier_number") or decision[5:] in linked:
                actions.append({"action": "skip", "number": row["number"], "name": row["name"],
                                "reason": "the supplier chosen to link to is not available"})
                continue
            linked.add(decision[5:])
            update_action(row, target_supplier, kind="link")
            continue
        if clash and decision != "create":
            duplicates.append({"number": row["number"], "name": row["name"], "country_code": row["country_code"],
                               "existing_id": str(clash["id"]), "existing_name": clash.get("name"),
                               "existing_code": clash.get("supplier_code")})
            actions.append({"action": "needs_decision", "number": row["number"], "name": row["name"],
                            "reason": f"same name as {clash.get('name')} ({clash.get('supplier_code')})"})
            continue
        actions.append({"action": "create", "number": row["number"], "name": row["name"],
                        "fields": {**_target(row), "supplier_code": f"SAP-{row['number']}", "aliases": row["aliases"]}})

    in_file = {r["number"] for r in rows}
    missing = [s for n, s in by_number.items() if n not in in_file and s.get("is_active", True)]
    previous = len(by_number)
    guard = None
    if deactivate_missing and missing:
        if previous and len(in_file) < MIN_RATIO * previous:
            guard = (f"The file has {len(in_file)} suppliers but {previous} were imported before, so missing "
                     f"suppliers were not deactivated. Check that the export is complete.")
        else:
            for s in missing:
                actions.append({"action": "deactivate", "number": s["sap_supplier_number"], "name": s.get("name"),
                                "supplier_id": str(s["id"]), "fields": {"is_active": False, "sap_missing": True},
                                "reason": "not in this SAP extract"})
    summary: Dict[str, int] = {}
    for a in actions:
        summary[a["action"]] = summary.get(a["action"], 0) + 1
    return {"summary": summary, "actions": actions, "duplicates": duplicates,
            "missing": [{"number": s["sap_supplier_number"], "name": s.get("name"), "supplier_id": str(s["id"])}
                        for s in missing],
            "missing_deactivated": bool(deactivate_missing and missing and guard is None),
            "guard": guard}
