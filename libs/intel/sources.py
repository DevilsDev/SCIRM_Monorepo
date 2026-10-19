"""
Connectors for free public sources. Each turns raw records into signals:

    {source, external_id, signal_type, title, summary, severity, entity_names,
     entity_keys, country_codes, occurred_at, published_at, updated_at, url, raw}

`published_at` is when the information became public, and `occurred_at` is when
the event happened (for a recall, initiation comes weeks before FDA publishes
it). Anything that reasons about what was knowable at a point in time, such as
back-tests or alerts, must use `published_at`; using `occurred_at` would credit
the system with knowing about events before they were announced.

Parsing is separate from fetching so it can be tested on recorded payloads.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from libs.intel.matching import entity_keys

OPENFDA = "https://api.fda.gov"
GDACS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
USER_AGENT = "SCIRM/1.0 (supply chain risk monitoring)"
PAGE = 1000

# Country names as openFDA writes them.
COUNTRY_CODES = {
    "united states": "US", "india": "IN", "china": "CN", "canada": "CA", "vietnam": "VN", "viet nam": "VN",
    "korea (the republic of)": "KR", "korea, republic of": "KR", "south korea": "KR", "taiwan": "TW",
    "australia": "AU", "croatia": "HR", "ireland": "IE", "japan": "JP", "germany": "DE", "france": "FR",
    "italy": "IT", "spain": "ES", "switzerland": "CH", "united kingdom": "GB", "israel": "IL", "mexico": "MX",
    "brazil": "BR", "netherlands": "NL", "belgium": "BE", "denmark": "DK", "sweden": "SE", "austria": "AT",
    "poland": "PL", "hungary": "HU", "slovenia": "SI", "singapore": "SG", "malaysia": "MY", "thailand": "TH",
    "indonesia": "ID", "pakistan": "PK", "bangladesh": "BD", "turkey": "TR", "puerto rico": "PR",
    "portugal": "PT", "greece": "GR", "czech republic": "CZ", "czechia": "CZ", "finland": "FI", "norway": "NO",
}
RECALL_SEVERITY = {"Class I": "critical", "Class II": "high", "Class III": "medium"}
AVAILABILITY_SEVERITY = {"unavailable": "high", "unvailable": "high", "limited availability": "medium", "available": "low"}


@dataclass
class SourceResult:
    source: str
    signals: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok | error | rate_limited
    error: Optional[str] = None


def _ymd(value: Optional[str]) -> Optional[str]:
    """openFDA enforcement dates: 20260930 -> 2026-09-30."""
    if value and re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return None


def _mdy(value: Optional[str]) -> Optional[str]:
    """openFDA shortage dates: 10/08/2026 -> 2026-10-08."""
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat() if value else None
    except ValueError:
        return None


def _signal(**fields: Any) -> Dict[str, Any]:
    fields.setdefault("updated_at", fields.get("published_at"))
    fields["entity_keys"] = entity_keys(fields.get("entity_names") or [])
    return fields


# --- openFDA drug recalls (enforcement reports) -----------------------------

def parse_recall(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    number = r.get("recall_number")
    published = _ymd(r.get("report_date"))
    if not number or not published:
        return None
    openfda = r.get("openfda") or {}
    product = ", ".join((openfda.get("brand_name") or openfda.get("generic_name") or [])[:2]) \
        or (r.get("product_description") or "").split(",")[0][:80]
    classification = r.get("classification") or "Unclassified"
    firm = r.get("recalling_firm") or ""
    country = COUNTRY_CODES.get((r.get("country") or "").strip().lower())
    return _signal(
        source="fda_recalls", external_id=number, signal_type="recall",
        title=f"{classification} recall: {product}".strip(),
        summary=f"{firm}: {r.get('reason_for_recall') or 'reason not stated'}. "
                f"Status: {r.get('status') or 'unknown'}. Distribution: {r.get('distribution_pattern') or 'unknown'}.",
        severity=RECALL_SEVERITY.get(classification, "medium"),
        entity_names=list(dict.fromkeys([firm] + list(openfda.get("manufacturer_name") or []))),
        country_codes=[country] if country else [],
        occurred_at=_ymd(r.get("recall_initiation_date")) or published,
        published_at=published,
        url=f'{OPENFDA}/drug/enforcement.json?search=recall_number:"{number}"',
        raw={k: r.get(k) for k in ("recall_number", "classification", "recalling_firm", "reason_for_recall",
                                   "status", "product_description", "product_quantity", "country",
                                   "recall_initiation_date", "center_classification_date", "report_date",
                                   "voluntary_mandated", "distribution_pattern")},
    )


async def fetch_recalls(client: httpx.AsyncClient, since: date, until: date) -> SourceResult:
    search = f"report_date:[{since:%Y%m%d} TO {until:%Y%m%d}]"
    records = await _openfda_all(client, "/drug/enforcement.json", search)
    return SourceResult("fda_recalls", [s for s in map(parse_recall, records) if s])


# --- openFDA drug shortages -------------------------------------------------

def _shortage_severity(counts: Dict[str, int]) -> str:
    """From availability, not status: most "Current" listings are still available.
    High only when at least half the presentations are unavailable."""
    total = sum(counts.values()) or 1
    unavailable = sum(n for k, n in counts.items() if AVAILABILITY_SEVERITY.get(k.lower()) == "high")
    if unavailable / total >= 0.5:
        return "high"
    if unavailable or any(AVAILABILITY_SEVERITY.get(k.lower()) == "medium" for k in counts):
        return "medium"
    return "low"


def parse_shortages(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One signal per (company, drug): FDA lists each package separately."""
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in records:
        company, drug = (r.get("company_name") or "").strip(), (r.get("generic_name") or "").strip()
        if company and drug and r.get("status") in ("Current", "To Be Discontinued"):
            groups.setdefault((company, drug, r["status"]), []).append(r)

    signals = []
    for (company, drug, status), items in groups.items():
        published = min(filter(None, (_mdy(i.get("initial_posting_date")) for i in items)), default=None)
        if not published:
            continue
        counts: Dict[str, int] = {}
        for i in items:
            label = (i.get("availability") or "unknown").strip()
            counts[label] = counts.get(label, 0) + 1
        if status == "To Be Discontinued":
            signal_type, severity, title = "discontinuation", "medium", f"Discontinuation: {drug}"
        else:
            severity = _shortage_severity(counts)
            signal_type, title = "shortage", f"Shortage: {drug}"
        manufacturers = [m for i in items for m in ((i.get("openfda") or {}).get("manufacturer_name") or [])]
        signals.append(_signal(
            source="fda_shortages",
            external_id=hashlib.sha1(f"{company}|{drug}|{status}".lower().encode()).hexdigest()[:20],
            signal_type=signal_type, title=title,
            summary=f"{company}: {', '.join(f'{n} {k.lower()}' for k, n in sorted(counts.items()))} "
                    f"(FDA status: {status}).",
            severity=severity,
            entity_names=list(dict.fromkeys([company] + manufacturers)),
            country_codes=[],
            occurred_at=published, published_at=published,
            updated_at=max(filter(None, (_mdy(i.get("update_date")) for i in items)), default=published),
            url="https://dps.fda.gov/drugshortages",
            raw={"company_name": company, "generic_name": drug, "status": status, "availability": counts,
                 "presentations": len(items),
                 "therapeutic_category": sorted({c for i in items for c in (i.get("therapeutic_category") or [])})},
        ))
    return signals


async def fetch_shortages(client: httpx.AsyncClient, since: date, until: date) -> SourceResult:
    # A current snapshot: FDA publishes no history, so every run re-reads the full active list.
    records = await _openfda_all(client, "/drug/shortages.json", 'status:"Current" status:"To Be Discontinued"')
    return SourceResult("fda_shortages", parse_shortages(records))


# --- GDACS natural disasters ------------------------------------------------

GDACS_TYPES = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano",
               "DR": "Drought", "WF": "Wildfire"}


def parse_gdacs(feature: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = feature.get("properties") or {}
    if p.get("alertlevel") not in ("Orange", "Red") or not p.get("eventid"):
        return None
    published = (p.get("fromdate") or "")[:10] or None
    if not published:
        return None
    countries = sorted({c.get("iso2") for c in (p.get("affectedcountries") or []) if c.get("iso2")})
    description = re.sub(r"<[^>]+>", "", p.get("htmldescription") or p.get("description") or "").strip()
    severity_text = (p.get("severitydata") or {}).get("severitytext")
    return _signal(
        source="gdacs", external_id=f"{p.get('eventtype')}-{p['eventid']}", signal_type="disaster",
        title=p.get("name") or f"{GDACS_TYPES.get(p.get('eventtype'), 'Disaster')} alert",
        summary=" ".join(filter(None, [description, severity_text])),
        severity="critical" if p["alertlevel"] == "Red" else "high",
        entity_names=[], country_codes=countries,
        occurred_at=published, published_at=published,
        updated_at=(p.get("datemodified") or "")[:10] or published,
        url=(p.get("url") or {}).get("report"),
        raw={k: p.get(k) for k in ("eventtype", "eventid", "episodeid", "alertlevel", "country", "fromdate",
                                   "todate", "datemodified", "severitydata")},
    )


async def fetch_gdacs(client: httpx.AsyncClient, since: date, until: date) -> SourceResult:
    response = await client.get(GDACS, params={"alertlevel": "Orange;Red", "fromDate": since.isoformat(),
                                               "toDate": until.isoformat()})
    if response.status_code == 204:  # GDACS answers 204 when nothing matches
        return SourceResult("gdacs", [])
    response.raise_for_status()
    features = response.json().get("features") or []
    return SourceResult("gdacs", [s for s in map(parse_gdacs, features) if s])


# --- shared -------------------------------------------------------------------

async def _openfda_all(client: httpx.AsyncClient, path: str, search: str) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"search": search, "limit": PAGE}
    if os.getenv("OPENFDA_API_KEY"):
        params["api_key"] = os.environ["OPENFDA_API_KEY"]
    records: List[Dict[str, Any]] = []
    skip = 0
    while True:
        response = await client.get(f"{OPENFDA}{path}", params={**params, "skip": skip})
        if response.status_code == 404:  # openFDA's answer to "no matches"
            return records
        response.raise_for_status()
        body = response.json()
        batch = body.get("results") or []
        records.extend(batch)
        total = ((body.get("meta") or {}).get("results") or {}).get("total", 0)
        skip += len(batch)
        if not batch or skip >= total or skip >= 25000:  # openFDA's skip ceiling
            return records


SOURCES: Dict[str, Callable] = {
    "fda_recalls": fetch_recalls,
    "fda_shortages": fetch_shortages,
    "gdacs": fetch_gdacs,
}
SOURCE_LABELS = {"fda_recalls": "FDA drug recalls", "fda_shortages": "FDA drug shortages",
                 "gdacs": "GDACS disaster alerts"}


async def collect(client: httpx.AsyncClient, lookback_days: int, today: Optional[date] = None,
                  only: Optional[List[str]] = None) -> List[SourceResult]:
    """Fetch every source. A failing source is reported, never replaced with sample data."""
    today = today or datetime.now(timezone.utc).date()
    since = today - timedelta(days=lookback_days)
    results = []
    for name, fetch in SOURCES.items():
        if only and name not in only:
            continue
        try:
            results.append(await fetch(client, since, today))
        except httpx.HTTPStatusError as exc:
            status = "rate_limited" if exc.response.status_code == 429 else "error"
            results.append(SourceResult(name, status=status, error=f"HTTP {exc.response.status_code}"))
        except (httpx.HTTPError, ValueError) as exc:
            results.append(SourceResult(name, status="error", error=type(exc).__name__))
    return results


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
