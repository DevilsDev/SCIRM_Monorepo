"""
Supplier scan: a list of suppliers in, a report of their public records out.

Used for prospects (scripts/supplier_scan.py, nothing stored) and by customers in
the app. It applies the same rules as the rest of SCIRM:
- the supplier matcher, which reports how each record matched; similar-name matches
  are marked for checking;
- the back-tested Watch flag (libs/intel/scoring.py);
- country-only matches are exposures, never incidents;
- "no records" names the sources and dates searched; it is not a clean bill of health.
"""

import csv
import html
import io
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from libs.intel import matching, scoring
from libs.intel.sources import IMPORT_ALERT_COUNTRIES, SOURCE_LABELS

MAX_SUPPLIERS = 500
MIN_CONFIDENCE = 0.6
EXPOSURE_DAYS = 30
NAME_COLUMNS = ("name", "supplier", "supplier name", "supplier_name", "company", "company name", "vendor",
                "vendor name", "manufacturer")
COUNTRY_COLUMNS = ("country", "country code", "country_code", "country/region", "location")
ALIAS_COLUMNS = ("aliases", "alias", "other names", "also known as", "aka", "trading names")
TYPE_ORDER = ["import_alert", "recall", "warning_letter", "shortage", "discontinuation"]
TYPE_LABELS = {"recall": "FDA recalls", "warning_letter": "FDA warning letters",
               "import_alert": "FDA import alerts (current Red List)", "shortage": "FDA drug shortages (current list)",
               "discontinuation": "FDA discontinuation notices (current list)"}
WATCH_EXPLANATION = (
    "Watch: recent FDA recall history at the level that, in back-tests on 2023-2026 data, came at least 30 days "
    "before about 4 in 10 serious (Class I) recalls at firms with FDA history. Most watched suppliers do not go on "
    "to have one; treat it as a reason to look closer, not a prediction.")


# --- input ----------------------------------------------------------------

def _country_code(value: str) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None
    if re.fullmatch(r"[A-Za-z]{2}", value):
        return value.upper()
    return IMPORT_ALERT_COUNTRIES.get(value.lower())


def parse_supplier_csv(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Suppliers from a CSV export (comma or semicolon separated, header row required).

    Returns (suppliers, warnings). A name column is required; country and aliases
    (separated by ';' or '|') are optional.
    """
    text = (text or "").lstrip("﻿")
    if not text.strip():
        return [], ["The file is empty."]
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    header = [h.strip().lower() for h in rows[0]]

    def col(options):
        return next((i for i, h in enumerate(header) if h in options), None)

    name_i, country_i, alias_i = col(NAME_COLUMNS), col(COUNTRY_COLUMNS), col(ALIAS_COLUMNS)
    if name_i is None:
        return [], [f"No supplier name column found. Use a header such as 'name' or 'supplier' "
                    f"(found: {', '.join(rows[0]) or 'nothing'})."]
    warnings, suppliers, seen = [], [], set()
    for line, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        name = row[name_i].strip() if name_i < len(row) else ""
        if not name:
            warnings.append(f"Row {line}: no name; skipped.")
            continue
        if matching.normalize(name) in seen:
            warnings.append(f"Row {line}: {name} appears more than once; scanned once.")
            continue
        seen.add(matching.normalize(name))
        country_raw = row[country_i].strip() if country_i is not None and country_i < len(row) else ""
        country = _country_code(country_raw)
        if country_raw and not country:
            warnings.append(f"Row {line}: country '{country_raw}' not recognised; disaster exposure skipped for {name}.")
        aliases = []
        if alias_i is not None and alias_i < len(row):
            aliases = [a.strip() for a in re.split(r"[;|]", row[alias_i]) if a.strip()][:20]
        suppliers.append({"id": f"row-{line}", "name": name[:255], "country_code": country, "aliases": aliases})
        if len(suppliers) >= MAX_SUPPLIERS:
            warnings.append(f"Only the first {MAX_SUPPLIERS} suppliers were scanned.")
            break
    return suppliers, warnings


# --- scan -----------------------------------------------------------------

def _record(signal: Dict[str, Any], m: Dict[str, Any]) -> Dict[str, Any]:
    raw = signal.get("raw") or {}
    return {
        "type": signal["signal_type"], "source": SOURCE_LABELS.get(signal["source"], signal["source"]),
        "title": signal["title"], "summary": signal.get("summary") or "", "severity": signal["severity"],
        "published_at": str(signal["published_at"])[:10], "url": signal.get("url"),
        "classification": raw.get("classification"), "event_id": raw.get("event_id"),
        "match": m["match_type"], "matched_on": m["matched_on"],
        "check": m["match_type"] in ("name_similar", "name_contains", "parent_company"),
    }


async def run_scan(store, suppliers: List[Dict[str, Any]], as_of: Optional[date] = None,
                   coverage: Optional[str] = None) -> Dict[str, Any]:
    """Match each supplier against the public records in `store`."""
    as_of = as_of or datetime.now(timezone.utc).date()
    exposure_since = (as_of - timedelta(days=EXPOSURE_DAYS)).isoformat()
    results = []
    for supplier in suppliers:
        index = matching.supplier_index([supplier])
        candidates = await store.signal_candidates(index["keys"], index["countries"], limit=20000)
        incidents, exposures = [], []
        for signal in candidates:
            m = matching.match_supplier(supplier, signal)
            if not m:
                continue
            if m["kind"] == "exposure":
                if (signal.get("updated_at") or signal["published_at"]) >= exposure_since:
                    exposures.append(signal)
            elif m["confidence"] >= MIN_CONFIDENCE:
                incidents.append({**m, "signal": signal})
        watch = scoring.watch_from_matches(incidents, as_of)
        # Grouped by type (most serious kinds first), newest first within each type.
        records = sorted((_record(i["signal"], i) for i in incidents), key=lambda r: r["published_at"], reverse=True)
        records.sort(key=lambda r: TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 99)
        results.append({
            "name": supplier["name"], "country_code": supplier.get("country_code"),
            "aliases": supplier.get("aliases") or [],
            "watch": watch["watch"], "recall_score": watch["recall_score"],
            "counts": dict(Counter(r["type"] for r in records)),
            # One FDA recall event often covers many products, each with its own notice.
            "recall_events": len({r["event_id"] or r["title"] for r in records if r["type"] == "recall"}),
            "records": records,
            "exposures": [{"title": e["title"], "published_at": str(e["published_at"])[:10], "url": e.get("url"),
                           "severity": e["severity"]} for e in sorted(exposures, key=lambda e: e["published_at"],
                                                                       reverse=True)[:5]],
        })
    results.sort(key=lambda r: (not r["watch"], -len(r["records"]), r["name"].lower()))
    totals = Counter()
    for r in results:
        totals.update(r["counts"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "as_of": as_of.isoformat(),
        "coverage": coverage, "suppliers": results,
        "summary": {"scanned": len(results), "with_records": sum(1 for r in results if r["records"]),
                    "watch": sum(1 for r in results if r["watch"]), "by_type": dict(totals),
                    "to_check": sum(1 for r in results for rec in r["records"] if rec["check"])},
    }


# --- report ---------------------------------------------------------------

def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _link(url: Optional[str], text: str) -> str:
    if url and url.startswith(("https://", "http://")):
        return f'<a href="{_e(url)}" rel="noopener noreferrer">{_e(text)}</a>'
    return _e(text)


def render_html(report: Dict[str, Any], title: str = "Supplier risk scan", prepared_for: str = "") -> str:
    """A self-contained, printable HTML report (no scripts, no external resources)."""
    s = report["summary"]
    by_type = ", ".join(f"{n} {TYPE_LABELS.get(t, t).split(' (')[0].lower()}" for t, n in
                        sorted(s["by_type"].items(), key=lambda kv: TYPE_ORDER.index(kv[0]) if kv[0] in TYPE_ORDER else 99))
    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>
:root {{ --ink:#1f2933; --muted:#616e7c; --line:#e4e7eb; --watch:#b45309; --bg:#fff; }}
body {{ font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg);
       max-width: 960px; margin: 0 auto; padding: 32px 16px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }} h2 {{ font-size: 17px; margin: 0; }} h3 {{ font-size: 13px; margin: 14px 0 4px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
.muted {{ color: var(--muted); }} .small {{ font-size: 12px; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 20px 0; }}
.stat {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; }} .stat b {{ font-size: 22px; display: block; }}
.supplier {{ border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin: 12px 0; break-inside: avoid; }}
.badge {{ display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 4px; margin-left: 6px; vertical-align: middle; }}
.watch {{ background: #fef3c7; color: var(--watch); }} .check {{ background: #e0e7ff; color: #3730a3; }}
.sev-critical {{ color: #b91c1c; font-weight: 600; }} .sev-high {{ color: #c2410c; font-weight: 600; }}
ul {{ margin: 4px 0; padding-left: 18px; }} li {{ margin: 3px 0; }}
.method {{ border-top: 1px solid var(--line); margin-top: 28px; padding-top: 12px; }}
@media print {{ body {{ padding: 0; }} a {{ color: inherit; }} }}
</style></head><body>
<h1>{_e(title)}</h1>
<p class="muted">{_e(('Prepared for ' + prepared_for + ' · ') if prepared_for else '')}Generated {_e(report['generated_at'])} from public records{(' (' + _e(report['coverage']) + ')') if report.get('coverage') else ''}.</p>
<div class="summary">
<div class="stat"><b>{s['scanned']}</b>suppliers scanned</div>
<div class="stat"><b>{s['with_records']}</b>with public records</div>
<div class="stat"><b>{s['watch']}</b>on Watch</div>
<div class="stat"><b>{s['to_check']}</b>similar-name matches to check</div>
</div>
<p>{_e(by_type) if by_type else 'No FDA records name these suppliers in the sources searched.'}</p>"""]
    for r in report["suppliers"]:
        badges = '<span class="badge watch">WATCH</span>' if r["watch"] else ""
        country = f' <span class="muted small">{_e(r["country_code"])}</span>' if r.get("country_code") else ""
        parts.append(f'<section class="supplier"><h2>{_e(r["name"])}{country}{badges}</h2>')
        if r["aliases"]:
            parts.append(f'<p class="muted small">Also searched as: {_e(", ".join(r["aliases"]))}</p>')
        if not r["records"]:
            parts.append('<p class="muted">No FDA recall, warning letter, import alert or shortage record names this '
                         'supplier in the sources searched. That is not proof that nothing happened: records may be '
                         'under another name (add it as an alias).</p>')
        current = None
        for rec in r["records"]:
            if rec["type"] != current:
                if current is not None:
                    parts.append("</ul>")
                current = rec["type"]
                count = r["counts"].get(current, 0)
                label = (f"{count} notices in {r['recall_events']} recall events"
                         if current == "recall" and r["recall_events"] != count else str(count))
                parts.append(f'<h3>{_e(TYPE_LABELS.get(current, current))} · {_e(label)}</h3><ul>')
            check = (' <span class="badge check">CHECK NAME</span>' if rec["check"] else "")
            matched = f' <span class="muted small">(record names "{_e(rec["matched_on"])}")</span>' if rec["check"] else ""
            parts.append(f'<li><span class="sev-{_e(rec["severity"])}">{_e(rec["published_at"])}</span> · '
                         f'{_link(rec["url"], rec["title"])}{check}<br><span class="muted small">{_e(rec["summary"][:300])}'
                         f'</span>{matched}</li>')
        if current is not None:
            parts.append("</ul>")
        if r["exposures"]:
            items = "".join(f'<li>since {_e(e["published_at"])} · {_link(e["url"], e["title"])}</li>' for e in r["exposures"])
            parts.append(f'<h3>Possible exposure: disaster alerts in {_e(r["country_code"])} active in the last {EXPOSURE_DAYS} days</h3>'
                         f'<ul>{items}</ul><p class="muted small">These cover the whole country; they do not mean this '
                         f'supplier is affected.</p>')
        parts.append("</section>")
    parts.append(f"""<div class="method small muted">
<p><b>Sources:</b> FDA drug recalls (enforcement reports), FDA warning letters, FDA import alert Red Lists (drugs,
biologics, devices), FDA drug shortage and discontinuation lists, and GDACS disaster alerts. Each item links to the
public record.</p>
<p><b>Matching:</b> company names are compared after removing legal suffixes and formatting. Items marked
"CHECK NAME" matched a similar or parent-company name and should be confirmed before you rely on them.</p>
<p><b>{_e(WATCH_EXPLANATION)}</b></p>
<p>Generated by SCIRM. Public records can be incomplete or delayed; verify anything material at the source.</p>
</div></body></html>""")
    return "\n".join(parts)
