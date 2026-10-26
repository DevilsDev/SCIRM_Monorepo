"""
Who owns a supplier, from the Global LEI Index (GLEIF), published under CC0 1.0.

A Legal Entity Identifier (LEI) record holds an entity's legal name, addresses and status
("Level 1") and, where reported, its direct and ultimate accounting consolidating parent
("Level 2": the parents that consolidate it in their financial statements). When an entity
reports no parent, it gives one of GLEIF's exception reasons instead, such as "controlled by
natural persons". An entity that never reported either is "not reported", which is unknown,
not "independent".

SCIRM never links a supplier to an LEI by itself. A name and country search returns
candidates; a person confirms one. Coverage is thin for many smaller suppliers and outside
the EU and US: "no LEI found" means unknown.

GLEIF asks users not to imply its endorsement; SCIRM names it as the source and links each
record. Calls go to GLEIF_API_URL (default https://api.gleif.org/api/v1), without redirects.
"""

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

API = os.getenv("GLEIF_API_URL", "https://api.gleif.org/api/v1").rstrip("/")
TIMEOUT = 15.0
MAX_CANDIDATES = 10
LEI_PATTERN = re.compile(r"^[A-Z0-9]{18}[0-9]{2}$")

SOURCE = {
    "name": "GLEIF Global LEI Index",
    "url": "https://search.gleif.org/",
    "licence": "CC0 1.0",
    "licence_url": "https://www.gleif.org/en/meta/lei-data-terms-of-use",
    "note": "Data from the Global Legal Entity Identifier Foundation. GLEIF does not endorse SCIRM.",
}

# GLEIF's reporting exception reasons (Reporting Exceptions format 2.1).
EXCEPTION_REASONS = {
    "NATURAL_PERSONS": "No parent under GLEIF's definition: controlled by one or more natural persons "
                       "without an intermediate consolidating entity.",
    "NON_CONSOLIDATING": "No parent under GLEIF's definition: controlled by entities that do not prepare "
                         "consolidated financial statements.",
    "NO_KNOWN_PERSON": "No parent under GLEIF's definition: no known person controls it (for example, "
                       "dispersed shareholding).",
    "NON_PUBLIC": "A parent exists, but its details are not public.",
    "NO_LEI": "A parent exists, but it has no LEI and did not consent to get one.",
}


class GleifUnavailable(Exception):
    """GLEIF could not be reached or answered with an error."""


def is_lei(text: str) -> bool:
    return bool(LEI_PATTERN.match((text or "").strip().upper()))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _address(addr: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    addr = addr or {}
    return {"city": addr.get("city"), "country": addr.get("country"), "region": addr.get("region")}


def entity_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """The fields SCIRM shows from one GLEIF lei-records item."""
    attrs = record.get("attributes") or {}
    entity, registration = attrs.get("entity") or {}, attrs.get("registration") or {}
    return {
        "lei": record.get("id") or attrs.get("lei"),
        "legal_name": (entity.get("legalName") or {}).get("name"),
        "legal_address": _address(entity.get("legalAddress")),
        "headquarters": _address(entity.get("headquartersAddress")),
        "legal_form": (entity.get("legalForm") or {}).get("id"),
        "entity_status": entity.get("status"),
        "registration_status": registration.get("status"),
        "last_update": registration.get("lastUpdateDate"),
        "next_renewal": registration.get("nextRenewalDate"),
        "corroboration": registration.get("corroborationLevel"),
        "url": f"https://search.gleif.org/#/record/{record.get('id') or attrs.get('lei')}",
    }


def parent_from(parent_record: Optional[Dict[str, Any]], exception: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One parent level: a reported parent, a reported exception, or not reported."""
    if parent_record:
        return {"kind": "parent", **entity_summary(parent_record)}
    if exception:
        reason = ((exception.get("attributes") or {}).get("reason") or "").upper()
        return {"kind": "exception", "reason": reason,
                "explanation": EXCEPTION_REASONS.get(reason, "GLEIF reports an exception: " + (reason or "unknown"))}
    return {"kind": "not_reported",
            "explanation": "Neither a parent nor an exception is reported. Ownership is unknown here."}


def shared_owners(links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Groups of two or more suppliers under the same top entity: the ultimate parent
    reported to GLEIF, or the supplier's own LEI when it reports none (so a supplier that
    owns another supplier groups with it). Suppliers whose parents are not reported or
    withheld can still share an owner that GLEIF does not show."""
    groups: Dict[str, Dict[str, Any]] = {}
    for link in links:
        snap = link.get("snapshot") or {}
        entity, top = snap.get("entity") or {}, snap.get("ultimate_parent") or {}
        if top.get("kind") == "parent" and top.get("lei"):
            owner, relation = top, "owned"
        else:
            owner, relation = entity, "is the owner"
        if not owner.get("lei"):
            continue
        group = groups.setdefault(owner["lei"], {
            "owner_lei": owner["lei"], "owner_name": owner.get("legal_name"),
            "owner_country": (owner.get("legal_address") or {}).get("country"), "owner_url": owner.get("url"),
            "suppliers": []})
        group["suppliers"].append({"supplier_id": link.get("supplier_id"), "supplier": link.get("supplier"),
                                   "lei": entity.get("lei"), "relation": relation})
    shared = [g for g in groups.values() if len({s["supplier_id"] for s in g["suppliers"]}) > 1]
    return sorted(shared, key=lambda g: (-len(g["suppliers"]), g["owner_name"] or ""))


class Client:
    """Thin GLEIF API client. `transport` lets tests swap in a fake."""

    def __init__(self, base: str = API, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base = base.rstrip("/")
        self.transport = transport

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT, follow_redirects=False,
                                         headers={"Accept": "application/vnd.api+json"}) as client:
                response = await client.get(f"{self.base}{path}", params=params)
        except httpx.HTTPError as exc:
            raise GleifUnavailable(f"GLEIF could not be reached ({type(exc).__name__})") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise GleifUnavailable(f"GLEIF answered {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise GleifUnavailable("GLEIF sent an unreadable answer") from exc

    async def search(self, name: str, country: Optional[str] = None) -> List[Dict[str, Any]]:
        """Candidate LEI records for a supplier name (or an LEI typed in), optionally in one
        country (ISO-2). Never more than MAX_CANDIDATES; the person picks one, or none."""
        text = (name or "").strip()
        if is_lei(text):
            found = await self._get(f"/lei-records/{quote(text.upper())}")
            return [entity_summary(found["data"])] if found and found.get("data") else []
        if len(text) < 2:
            return []
        params: Dict[str, Any] = {"filter[fulltext]": text[:200], "page[size]": MAX_CANDIDATES}
        if country and re.fullmatch(r"[A-Za-z]{2}", country):
            params["filter[entity.legalAddress.country]"] = country.upper()
        body = await self._get("/lei-records", params) or {}
        return [entity_summary(r) for r in (body.get("data") or [])[:MAX_CANDIDATES]]

    async def ownership(self, lei: str) -> Optional[Dict[str, Any]]:
        """The entity and both parent levels, or None if the LEI does not exist."""
        lei = lei.strip().upper()
        if not is_lei(lei):
            return None
        record = await self._get(f"/lei-records/{quote(lei)}")
        if not record or not record.get("data"):
            return None
        levels = {}
        for level in ("direct", "ultimate"):
            parent = await self._get(f"/lei-records/{quote(lei)}/{level}-parent")
            exception = None if parent else await self._get(f"/lei-records/{quote(lei)}/{level}-parent-reporting-exception")
            levels[level] = parent_from((parent or {}).get("data"), (exception or {}).get("data"))
        return {"entity": entity_summary(record["data"]), "direct_parent": levels["direct"],
                "ultimate_parent": levels["ultimate"], "fetched_at": _now(),
                "golden_copy": ((record.get("meta") or {}).get("goldenCopy") or {}).get("publishDate")}
