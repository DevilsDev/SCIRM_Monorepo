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
        raw={k: r.get(k) for k in ("recall_number", "event_id", "classification", "recalling_firm", "reason_for_recall",
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


# --- FDA warning letters ----------------------------------------------------

WARNING_LETTERS = "https://www.fda.gov/datatables/views/ajax"
WARNING_LETTERS_VIEW = {
    "view_display_id": "warning_letter_solr_block", "view_name": "warning_letter_solr_index",
    "view_path": "/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters",
    "search_api_fulltext": "", "field_letter_issue_datetime": "All", "draw": "1",
}
# Not relevant to drug, biologic or device supply chains.
WARNING_LETTER_EXCLUDED_OFFICES = ("Center for Tobacco Products",)


def _text(html: str) -> str:
    import html as html_lib
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()


def _time_attr(html: str) -> Optional[str]:
    found = re.search(r'datetime="(\d{4}-\d{2}-\d{2})', html or "")
    return found.group(1) if found else None


def product_area(office: str, subject: str) -> str:
    """drugs | biologics | devices | food | veterinary | other, from the issuing office,
    or from the subject for import and field offices that cover several areas."""
    o, s = office.lower(), subject.lower()
    if "drug evaluation" in o or "pharmaceutical quality" in o:
        return "drugs"
    if "biologics" in o:
        return "biologics"
    if "devices" in o:
        return "devices"
    if "veterinary" in o:
        return "veterinary"
    if "food" in o:
        return "food"
    if any(k in s for k in ("pharmaceutical", "drug", "compounding", "api ")):
        return "drugs"
    if any(k in s for k in ("device", "quality system", "ide)", "(ide")):
        return "devices"
    if any(k in s for k in ("fsvp", "haccp", "food", "seafood", "juice", "dietary")):
        return "food"
    return "other"


def parse_warning_letter(row: List[str]) -> Optional[Dict[str, Any]]:
    """One row of FDA's warning-letter index: [posted, letter issued, company link, office, subject, ...]."""
    if len(row) < 5:
        return None
    posted, issued = _time_attr(row[0]), _time_attr(row[1])
    link = re.search(r'href="([^"]+)"', row[2] or "")
    company, office, subject = _text(row[2]), _text(row[3]), _text(row[4])
    if not (posted and company and link):
        return None
    if any(office.startswith(x) for x in WARNING_LETTER_EXCLUDED_OFFICES):
        return None
    url = link.group(1) if link.group(1).startswith("http") else f"https://www.fda.gov{link.group(1)}"
    return _signal(
        source="fda_warning_letters", external_id=url.rstrip("/").rsplit("/", 1)[-1], signal_type="warning_letter",
        title=f"FDA warning letter: {subject or 'see letter'}",
        summary=f"{company}: warning letter from {office}" + (f" dated {issued}" if issued else "") + ".",
        # A manufacturing-practice (CGMP) finding bears directly on supply; marketing violations less so.
        severity="high" if "cgmp" in subject.lower() else "medium",
        entity_names=[company], country_codes=[],
        # FDA posts letters weeks after issuing them; the posting date is when it became public.
        occurred_at=issued or posted, published_at=posted,
        url=url,
        raw={"company": company, "office": office, "subject": subject, "letter_issue_date": issued, "posted_date": posted,
             "product_area": product_area(office, subject)},
    )


async def fetch_warning_letters(client: httpx.AsyncClient, since: date, until: date) -> SourceResult:
    signals: List[Dict[str, Any]] = []
    start, page = 0, 500
    while True:
        response = await client.get(WARNING_LETTERS, params={**WARNING_LETTERS_VIEW, "start": start, "length": page},
                                    headers={"X-Requested-With": "XMLHttpRequest"})
        response.raise_for_status()
        body = response.json()
        rows = body.get("data") or []
        parsed = [s for s in map(parse_warning_letter, rows) if s]
        signals.extend(s for s in parsed if s["published_at"] >= since.isoformat())
        oldest = min((_time_attr(r[0]) or "9999" for r in rows), default="0000")
        start += len(rows)
        # Newest first: stop once a page reaches back past the window.
        if not rows or oldest < since.isoformat() or start >= int(body.get("recordsTotal") or 0):
            return SourceResult("fda_warning_letters", signals)


# --- FDA import alerts (detention without physical examination) -------------

IMPORT_ALERTS = "https://www.accessdata.fda.gov/cms_ia/"
# 57: biologics, 66: drugs, 89: devices.
IMPORT_ALERT_SERIES = ("57-", "66-", "89-")
IMPORT_ALERT_COUNTRIES = {**COUNTRY_CODES, "korea, republic of (south)": "KR", "china (mainland)": "CN",
                          "united states of america": "US", "hong kong": "HK", "russia": "RU", "russian federation": "RU",
                          "united arab emirates": "AE", "egypt": "EG", "sri lanka": "LK", "nepal": "NP", "jordan": "JO",
                          "argentina": "AR", "colombia": "CO", "chile": "CL", "peru": "PE", "south africa": "ZA",
                          "nigeria": "NG", "kenya": "KE", "armenia": "AM", "ukraine": "UA", "romania": "RO",
                          "bulgaria": "BG", "lithuania": "LT", "latvia": "LV", "estonia": "EE", "slovakia": "SK",
                          "serbia": "RS", "new zealand": "NZ", "philippines": "PH", "dominican republic": "DO",
                          "guatemala": "GT", "costa rica": "CR", "el salvador": "SV", "honduras": "HN", "aruba": "AW",
                          "lebanon": "LB", "saudi arabia": "SA", "iran": "IR", "luxembourg": "LU", "cyprus": "CY",
                          "malta": "MT", "iceland": "IS", "bahamas": "BS", "jamaica": "JM", "ecuador": "EC",
                          "uruguay": "UY", "venezuela": "VE", "ghana": "GH", "morocco": "MA", "tunisia": "TN",
                          "hong kong sar": "HK", "dominican republic (the)": "DO", "ivory coast": "CI",
                          "british virgin islands": "VG", "vanuatu": "VU", "panama": "PA", "trinidad & tobago": "TT",
                          "curacao": "CW", "dominica": "DM", "saint lucia": "LC", "guyana": "GY", "togo": "TG",
                          "gibraltar": "GI", "azerbaijan": "AZ", "belize": "BZ", "macau": "MO", "macao": "MO",
                          "netherlands (the)": "NL", "philippines (the)": "PH", "united kingdom of great britain and "
                          "northern ireland (the)": "GB", "united states of america (the)": "US", "georgia": "GE",
                          "kazakhstan": "KZ", "uzbekistan": "UZ", "belarus": "BY", "moldova": "MD", "albania": "AL",
                          "north macedonia": "MK", "bosnia and herzegovina": "BA", "montenegro": "ME", "qatar": "QA",
                          "kuwait": "KW", "bahrain": "BH", "oman": "OM", "ethiopia": "ET", "uganda": "UG",
                          "tanzania": "TZ", "cameroon": "CM", "senegal": "SN", "haiti": "HT", "barbados": "BB",
                          "nicaragua": "NI", "paraguay": "PY", "bolivia": "BO", "cambodia": "KH", "laos": "LA",
                          "myanmar": "MM", "mongolia": "MN", "fiji": "FJ", "samoa": "WS", "tonga": "TO"}


def parse_import_alert_index(html: str) -> List[Dict[str, str]]:
    """Rows of FDA's import alert list: number, type, last update, page and title."""
    rows = []
    for number, kind, updated, page, title in re.findall(
            r"<tr>\s*<td>([^<]+)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td><a href=\"(importalert_\d+\.html)\">(.*?)</a>",
            html, flags=re.S):
        rows.append({"number": number.strip(), "type": kind.strip(), "updated": updated.strip(), "page": page,
                     "title": _text(title).strip('"“”� ')})
    return rows


def parse_import_alert(html: str, number: str, title: str, url: str) -> List[Dict[str, Any]]:
    """Firms on an alert's Red List, each published on its own date.

    Only the Red List counts: firms there are detained at the border. Green List
    firms are exempt (in good standing) and are skipped."""
    start = html.find('name="RedFirm"')
    if start < 0:
        return []
    end = len(html)
    # Section anchors only: the phrase "Green List" also appears in alert texts.
    for marker in ('name="GreenFirm"', 'name="YellowFirm"'):
        pos = html.find(marker, start)
        if pos >= 0:
            end = min(end, pos)
    section = html[start:end]
    signals = []
    country = None
    for match in re.finditer(r'<div class="center"><h4>([^<]+)</h4>|<div class="div-info">(.*?)</div>\s*</div>',
                             section, flags=re.S):
        if match.group(1):
            country = _text(match.group(1))
            continue
        block = match.group(2)
        name = re.search(r'<div class="div-name floatleft">(.*?)</div>', block, flags=re.S)
        published = re.search(r"Date Published\s*:\s*(\d{2}/\d{2}/\d{4})", block)
        if not (name and published):
            continue
        firm = _text(name.group(1))
        code = IMPORT_ALERT_COUNTRIES.get((country or "").lower())
        published_at = _mdy(published.group(1))
        signals.append(_signal(
            source="fda_import_alerts",
            external_id=hashlib.sha1(f"{number}|{firm}|{country}".lower().encode()).hexdigest()[:20],
            signal_type="import_alert",
            title=f"FDA import alert {number}: {title}"[:300],
            summary=f"{firm} ({country.title() if country else 'country not stated'}) is on the Red List of import "
                    f"alert {number}: its products may be detained at the US border without examination.",
            # Manufacturing-practice (GMP) alerts bear on a firm's ability to supply; others
            # (e.g. unapproved products marketed in the US) are a weaker supplier signal.
            severity="high" if "gmp" in title.lower() or "good manufacturing" in title.lower() else "medium",
            entity_names=[firm], country_codes=[code] if code else [],
            occurred_at=published_at, published_at=published_at,
            url=url, raw={"alert": number, "alert_title": title, "firm": firm, "country": country},
        ))
    return signals


async def fetch_import_alerts(client: httpx.AsyncClient, since: date, until: date) -> SourceResult:
    # A current snapshot: firms leave the Red List when FDA removes them, so every run reads it whole.
    index = await client.get(f"{IMPORT_ALERTS}ialist.html")
    index.raise_for_status()
    alerts = [a for a in parse_import_alert_index(index.text) if a["number"].startswith(IMPORT_ALERT_SERIES)]
    signals: List[Dict[str, Any]] = []
    for alert in alerts:
        url = f"{IMPORT_ALERTS}{alert['page']}"
        page = await client.get(url)
        page.raise_for_status()
        signals.extend(parse_import_alert(page.text, alert["number"], alert["title"], url))
    # Still listed as of this run: the activity date, so long-standing listings (some from
    # 2009) are not hidden by "last 12 months" filters. published_at keeps the listing date.
    for s in signals:
        s["updated_at"] = until.isoformat()
    return SourceResult("fda_import_alerts", signals)


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
    "fda_warning_letters": fetch_warning_letters,
    "fda_import_alerts": fetch_import_alerts,
    "gdacs": fetch_gdacs,
}
# Sources published as current lists (no history): entries missing from a run are delisted.
SNAPSHOT_SOURCES = frozenset({"fda_shortages", "fda_import_alerts"})
SOURCE_LABELS = {"fda_recalls": "FDA drug recalls", "fda_shortages": "FDA drug shortages",
                 "fda_warning_letters": "FDA warning letters", "fda_import_alerts": "FDA import alerts",
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
