"""
Direct connection to SAP S/4HANA over its standard OData V2 APIs.

Reads the same data the file imports take (libs/integrations/sap_import.py and
sap_spend.py), so the same preview, rules and apply step are used:

- Supplier master: API_BUSINESS_PARTNER, entity A_BusinessPartner for suppliers
  (Supplier ne ''), with its addresses (to_BusinessPartnerAddress) and supplier
  record (to_Supplier: blocks, deletion flag, VAT number). Communication
  scenario SAP_COM_0008 in S/4HANA Cloud.
- Purchase orders: API_PURCHASEORDER_PROCESS_SRV, entity A_PurchaseOrder with its
  items (to_PurchaseOrderItem), for orders dated in the last 365 days. Communication
  scenario SAP_COM_0053.

The key is the supplier number (LIFNR: Supplier), not the business partner number,
which can differ. It is what the LFA1 file import stores and what purchase orders
carry, so suppliers imported from files and from the connection are the same records.

Only reads (GET). Only S/4HANA: SAP ECC has no such APIs, so ECC customers use the file
import. Field names are those of SAP's published API model; each import first reads the
services' $metadata and stops with a clear message if a field it needs is missing.

Outbound safety. The base URL is entered by a tenant admin, so outside development:
HTTPS only; no credentials, query or fragment in the URL; the host must resolve only to
public addresses (no private, loopback, link-local or cloud metadata ranges); the
request goes to the address that was checked (the host name is kept for TLS
verification and the Host header), so a second DNS answer cannot redirect it; redirects
are not followed; and responses are capped in size. An SAP system that is only reachable
inside a private network needs a public endpoint (SAP API Management, BTP, or a reverse
proxy); the guard is not relaxed for it. Error messages give SAP's HTTP status, never
its response body, and never the password.
"""

import ipaddress
import os
import re
import socket
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from libs.integrations import sap_import, sap_spend

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
# Outside development the outbound guard above applies. Tests switch it on and off in code.
STRICT = _ENVIRONMENT not in {"development", "dev", "local", "test"}

BP_SERVICE = "/sap/opu/odata/sap/API_BUSINESS_PARTNER"
PO_SERVICE = "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV"

# Entity set -> properties read from it.
BP_FIELDS = ("BusinessPartner", "Supplier", "OrganizationBPName1", "OrganizationBPName2", "OrganizationBPName3",
             "OrganizationBPName4", "BusinessPartnerFullName")
ADDRESS_FIELDS = ("AddressID", "Country", "CityName", "ValidityStartDate", "ValidityEndDate")
SUPPLIER_FIELDS = ("Supplier", "SupplierName", "PostingIsBlocked", "PurchasingIsBlocked", "DeletionIndicator",
                   "VATRegistration")
PO_FIELDS = ("PurchaseOrder", "Supplier", "PurchaseOrderDate", "DocumentCurrency", "PurchasingDocumentDeletionCode")
ITEM_FIELDS = ("PurchaseOrderItem", "Plant", "DocumentCurrency", "PurchasingDocumentDeletionCode", "NetPriceAmount",
               "NetPriceQuantity", "OrderQuantity")
# Item net value. Newer releases have it; otherwise it is computed from price and quantity.
NET_AMOUNT = "NetAmount"

REQUIRED = {
    BP_SERVICE: {"A_BusinessPartner": BP_FIELDS, "A_BusinessPartnerAddress": ADDRESS_FIELDS,
                 "A_Supplier": SUPPLIER_FIELDS},
    PO_SERVICE: {"A_PurchaseOrder": PO_FIELDS, "A_PurchaseOrderItem": ITEM_FIELDS},
}
SCENARIO = {BP_SERVICE: "SAP_COM_0008 (business partners and suppliers)",
            PO_SERVICE: "SAP_COM_0053 (purchase orders)"}

SUPPLIER_PAGE = 500
ORDER_PAGE = 200
MAX_ORDERS = 200_000
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# Code-only hooks for tests: an httpx transport, and the DNS resolver. Never read from
# the environment, so configuration cannot route requests around the guard.
transport_factory: Optional[Callable[[], httpx.AsyncBaseTransport]] = None


def _system_resolve(host: str, port: int) -> List[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


resolve: Callable[[str, int], List[str]] = _system_resolve


class SapError(Exception):
    """A failure to show the person: what went wrong, without SAP's response body."""


# --- connection settings ------------------------------------------------------

def validate_base_url(url: str, strict: Optional[bool] = None) -> str:
    """The base URL in canonical form (no trailing slash), or SapError."""
    strict = STRICT if strict is None else strict
    url = (url or "").strip()
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise SapError("The SAP address is not a valid URL.")
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise SapError("The SAP address must start with https:// and name a host.")
    if strict and parts.scheme != "https":
        raise SapError("The SAP address must use https://.")
    if parts.username or parts.password or "@" in parts.netloc:
        raise SapError("Put the user name and password in their own fields, not in the address.")
    if parts.query or parts.fragment:
        raise SapError("The SAP address must not contain a query (?) or fragment (#).")
    if port is not None and not 0 < port < 65536:
        raise SapError("The SAP address has an invalid port.")
    path = parts.path.rstrip("/")
    if "/sap/opu/odata" in path.lower():
        raise SapError("Enter the system's base address only, e.g. https://my-s4.example.com, "
                       "without /sap/opu/odata/...")
    netloc = parts.hostname.lower() if not parts.port else f"{parts.hostname.lower()}:{parts.port}"
    if ":" in parts.hostname:  # IPv6 literal
        netloc = f"[{parts.hostname}]" + (f":{parts.port}" if parts.port else "")
    return f"{parts.scheme}://{netloc}{path}"


def validate_client(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    if value and not re.fullmatch(r"\d{3}", value):
        raise SapError("The SAP client is three digits, e.g. 100.")
    return value or None


def _public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def _target(base_url: str, strict: bool) -> Tuple[str, Optional[str]]:
    """(URL to send requests to, TLS/Host name). In strict mode the host is resolved,
    every address must be public, and the URL names the checked address."""
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if not strict:
        return base_url, None
    port = parts.port or 443
    try:
        addresses = [host] if _is_ip(host) else resolve(host, port)
    except (OSError, UnicodeError):
        raise SapError(f"The SAP host {host} could not be found (DNS).")
    if not addresses:
        raise SapError(f"The SAP host {host} could not be found (DNS).")
    if not all(_public(a) for a in addresses):
        raise SapError(f"The SAP host {host} resolves to a private or reserved address. SCIRM only connects "
                       "to SAP systems reachable on the public internet (for example through SAP API "
                       "Management, SAP BTP or a reverse proxy).")
    ip = addresses[0]
    literal = f"[{ip}]" if ":" in ip else ip
    return f"{parts.scheme}://{literal}:{port}{parts.path}", host


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


# --- HTTP ---------------------------------------------------------------------

class _Session:
    """GET requests to one SAP system with the outbound guard applied."""

    def __init__(self, connection: Dict[str, Any], strict: Optional[bool] = None):
        self.strict = STRICT if strict is None else strict
        self.base = validate_base_url(connection["base_url"], self.strict)
        self.host = urlsplit(self.base).hostname
        self.url, self.sni = _target(self.base, self.strict)
        headers = {"Accept": "application/json"}
        if connection.get("sap_client"):
            headers["sap-client"] = connection["sap_client"]
        if self.sni:
            headers["Host"] = urlsplit(self.base).netloc
        kwargs: Dict[str, Any] = {"timeout": TIMEOUT, "follow_redirects": False, "headers": headers,
                                  "auth": (connection["username"], connection["password"])}
        if transport_factory is not None:
            kwargs["transport"] = transport_factory()
        self.client = httpx.AsyncClient(**kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()

    async def get(self, service: str, path: str, params: Optional[Dict[str, str]] = None,
                  accept: str = "application/json") -> bytes:
        extensions = {"sni_hostname": self.sni} if self.sni else {}
        try:
            async with self.client.stream("GET", f"{self.url}{service}{path}", params=params,
                                          headers={"Accept": accept}, extensions=extensions) as response:
                if response.status_code != 200:
                    raise SapError(_status_message(response.status_code, service))
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise SapError("SAP sent a larger response than SCIRM accepts. Nothing was imported.")
                return bytes(body)
        except httpx.TimeoutException:
            raise SapError(f"SAP at {self.host} did not answer in time. Nothing was imported.")
        except httpx.ConnectError as exc:
            if "CERTIFICATE" in str(exc).upper() or "SSL" in str(exc).upper():
                raise SapError(f"The TLS certificate of {self.host} could not be verified.")
            raise SapError(f"Could not connect to SAP at {self.host}.")
        except httpx.HTTPError as exc:
            raise SapError(f"The request to SAP at {self.host} failed ({type(exc).__name__}).")

    async def json(self, service: str, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        import json
        raw = await self.get(service, path, params)
        try:
            return json.loads(raw)["d"]
        except (ValueError, KeyError, TypeError):
            raise SapError(f"SAP's answer from {service.rsplit('/', 1)[-1]} was not OData JSON. "
                           "Check the address points to the S/4HANA system.")


def _status_message(status: int, service: str) -> str:
    name = service.rsplit("/", 1)[-1]
    if status in (401, 403):
        return (f"SAP refused access to {name} (HTTP {status}). Check the user name and password, and that the "
                f"communication user is assigned to {SCENARIO[service]}.")
    if status == 404:
        return (f"SAP has no {name} service at this address (HTTP 404). Check the address, and that the "
                f"service is active ({SCENARIO[service]}).")
    if status in (301, 302, 303, 307, 308):
        return f"SAP redirected the request (HTTP {status}); enter the address it redirects to."
    return f"SAP returned HTTP {status} for {name}."


# --- $metadata ------------------------------------------------------------------

def properties_from_metadata(xml: bytes) -> Dict[str, set]:
    """Entity set name -> property names, from an OData V2 $metadata document."""
    head = xml[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in xml.upper():
        raise SapError("SAP's $metadata document contains a DTD, which SCIRM does not read.")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise SapError("SAP's $metadata document could not be read.")
    types: Dict[str, set] = {}
    sets: Dict[str, str] = {}
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "EntityType":
            types[el.get("Name", "")] = {p.get("Name") for p in el if p.tag.rsplit("}", 1)[-1] == "Property"}
        elif tag == "EntitySet":
            sets[el.get("Name", "")] = (el.get("EntityType") or "").rsplit(".", 1)[-1]
    return {name: types.get(t, set()) for name, t in sets.items()}


async def _check_metadata(session: _Session, service: str) -> Dict[str, set]:
    found = properties_from_metadata(await session.get(service, "/$metadata", accept="application/xml"))
    problems = []
    for entity, fields in REQUIRED[service].items():
        if entity not in found:
            problems.append(f"{entity} is missing")
            continue
        absent = [f for f in fields if f not in found[entity]]
        if absent:
            problems.append(f"{entity} has no {', '.join(absent)}")
    if problems:
        raise SapError(f"{service.rsplit('/', 1)[-1]} on this system does not have what SCIRM reads: "
                       f"{'; '.join(problems)}. Nothing was imported.")
    return found


# --- values ---------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_DATE = re.compile(r"^/Date\((-?\d+)(?:[+-]\d{4})?\)/$")


def parse_date(value: Any) -> Optional[date]:
    """Edm.DateTime / Edm.DateTimeOffset in OData V2 JSON ("/Date(1729468800000)/"), or ISO."""
    if not value:
        return None
    m = _DATE.match(str(value))
    if m:
        # Arithmetic rather than fromtimestamp(): SAP's "valid to" is 9999-12-31, out of the
        # platform range on some systems.
        try:
            return (_EPOCH + timedelta(milliseconds=int(m[1]))).date()
        except OverflowError:
            return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _flag(value: Any) -> str:
    """OData booleans and SAP indicators as the LFA1 flag strings sap_import reads."""
    if isinstance(value, bool):
        return "X" if value else ""
    return str(value or "").strip()


def _results(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        return value.get("results") or []
    return value or []


def _address(addresses: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    """The address valid today with the lowest id (the standard address is usually the
    first), else the first one."""
    def valid(a):
        start, end = parse_date(a.get("ValidityStartDate")), parse_date(a.get("ValidityEndDate"))
        return (start is None or start <= today) and (end is None or end >= today)
    ordered = sorted(addresses, key=lambda a: str(a.get("AddressID") or ""))
    return next((a for a in ordered if valid(a)), ordered[0] if ordered else {})


def supplier_fields(bp: Dict[str, Any], today: date) -> Dict[str, str]:
    """One A_BusinessPartner (with expanded supplier and addresses) as LFA1 fields."""
    supplier = bp.get("to_Supplier") or {}
    address = _address(_results(bp.get("to_BusinessPartnerAddress")), today)
    name1 = bp.get("OrganizationBPName1") or bp.get("BusinessPartnerFullName") or supplier.get("SupplierName") or ""
    return {
        "number": supplier.get("Supplier") or bp.get("Supplier") or "",
        "name1": name1, "name2": bp.get("OrganizationBPName2") or "", "name3": bp.get("OrganizationBPName3") or "",
        "name4": bp.get("OrganizationBPName4") or "",
        "country": address.get("Country") or "", "city": address.get("CityName") or "",
        "posting_block": _flag(supplier.get("PostingIsBlocked")),
        "purchasing_block": _flag(supplier.get("PurchasingIsBlocked")),
        "deletion_flag": _flag(supplier.get("DeletionIndicator")),
        "vat_number": supplier.get("VATRegistration") or "",
    }


def order_lines(po: Dict[str, Any], net_amount: bool) -> Tuple[List[Dict[str, Any]], int]:
    """One A_PurchaseOrder's items as spend lines (as sap_spend.parse_po_extract makes
    them), and how many items had no readable value."""
    number = sap_import.normalize_number(po.get("Supplier") or "")
    when = parse_date(po.get("PurchaseOrderDate"))
    header_deleted = bool(_flag(po.get("PurchasingDocumentDeletionCode")))
    lines, unreadable = [], 0
    for item in _results(po.get("to_PurchaseOrderItem")):
        amount = _decimal(item.get(NET_AMOUNT)) if net_amount else None
        if amount is None:
            price, quantity = _decimal(item.get("NetPriceAmount")), _decimal(item.get("OrderQuantity"))
            per = _decimal(item.get("NetPriceQuantity"))
            if price is not None and quantity is not None:
                amount = price * quantity / (per if per else Decimal(1))
        currency = (item.get("DocumentCurrency") or po.get("DocumentCurrency") or "").upper()
        if not number or when is None or amount is None or not re.fullmatch(r"[A-Z]{3}", currency):
            unreadable += 1
            continue
        lines.append({"number": number, "date": when, "amount": amount, "currency": currency,
                      "document": po.get("PurchaseOrder") or None, "plant": item.get("Plant") or None,
                      "deleted": header_deleted or bool(_flag(item.get("PurchasingDocumentDeletionCode"))),
                      "line": f"{po.get('PurchaseOrder')}/{item.get('PurchaseOrderItem')}"})
    return lines, unreadable


# --- reading ----------------------------------------------------------------------

def _page_query(params: Dict[str, str], top: int, skip: int, order_by: str, count: bool) -> Dict[str, str]:
    query = {**params, "$format": "json", "$top": str(top), "$skip": str(skip), "$orderby": order_by}
    if count:
        query["$inlinecount"] = "allpages"
    return query


async def _pages(session: _Session, service: str, entity: str, params: Dict[str, str], page: int,
                 limit: int, order_by: str) -> Tuple[List[Dict[str, Any]], int]:
    """All records of a query, in pages, and the total SAP reported. Raises if a page
    fails or SAP returns fewer records than it counted, so a partial list is never
    planned (a short supplier list would read as suppliers removed from SAP)."""
    records: List[Dict[str, Any]] = []
    total: Optional[int] = None
    skip = 0
    while True:
        data = await session.json(service, f"/{entity}", _page_query(params, page, skip, order_by, total is None))
        if total is None:
            try:
                total = int(data.get("__count"))
            except (TypeError, ValueError):
                raise SapError(f"SAP did not report how many {entity} records there are. Nothing was imported.")
            if total > limit:
                raise SapError(f"SAP has {total} {entity} records for this import, more than the {limit} SCIRM "
                               "reads in one import. Nothing was imported.")
        batch = data.get("results") or []
        records += batch
        skip += len(batch)
        if not batch or skip >= total:
            break
    if len(records) != total:
        raise SapError(f"SAP counted {total} {entity} records but returned {len(records)}. Nothing was imported.")
    return records, total


def _select(entity_fields, nav: Dict[str, Tuple[str, ...]]) -> Dict[str, str]:
    fields = list(entity_fields) + [f"{n}/{f}" for n, fs in nav.items() for f in fs]
    return {"$select": ",".join(fields), "$expand": ",".join(nav)}


def _supplier_query() -> Tuple[str, Dict[str, str], str]:
    """(entity, query, order) of the supplier read; the connection test sends the same."""
    return "A_BusinessPartner", {
        "$filter": "Supplier ne ''",
        **_select(BP_FIELDS, {"to_Supplier": SUPPLIER_FIELDS, "to_BusinessPartnerAddress": ADDRESS_FIELDS}),
    }, "BusinessPartner"


def _order_query(today: date, net_amount: bool) -> Tuple[str, Dict[str, str], str]:
    """(entity, query, order) of the purchase-order read for the 365 days up to today."""
    start = today - timedelta(days=sap_spend.PERIOD_DAYS - 1)
    items = ITEM_FIELDS + ((NET_AMOUNT,) if net_amount else ())
    return "A_PurchaseOrder", {
        "$filter": f"PurchaseOrderDate ge datetime'{start.isoformat()}T00:00:00'",
        **_select(PO_FIELDS, {"to_PurchaseOrderItem": items}),
    }, "PurchaseOrder"


async def fetch_suppliers(connection: Dict[str, Any], today: Optional[date] = None,
                          strict: Optional[bool] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Supplier rows (as sap_import.parse_extract returns them) read from SAP."""
    today = today or date.today()
    async with _Session(connection, strict) as session:
        await _check_metadata(session, BP_SERVICE)
        entity, params, order_by = _supplier_query()
        records, _ = await _pages(session, BP_SERVICE, entity, params, SUPPLIER_PAGE, sap_import.MAX_ROWS, order_by)
    return sap_import.build_rows(((supplier_fields(bp, today), bp.get("BusinessPartner")) for bp in records),
                                 "Business partner")


async def fetch_orders(connection: Dict[str, Any], today: Optional[date] = None,
                       strict: Optional[bool] = None) -> Tuple[List[Dict[str, Any]], List[str], date]:
    """Spend lines for purchase orders dated in the 365 days up to today, the warnings,
    and the period's end (today), for sap_spend.summarize(lines, end=...)."""
    today = today or date.today()
    async with _Session(connection, strict) as session:
        found = await _check_metadata(session, PO_SERVICE)
        net_amount = NET_AMOUNT in found["A_PurchaseOrderItem"]
        entity, params, order_by = _order_query(today, net_amount)
        orders, _ = await _pages(session, PO_SERVICE, entity, params, ORDER_PAGE, MAX_ORDERS, order_by)
    lines, unreadable = [], 0
    for po in orders:
        got, bad = order_lines(po, net_amount)
        lines += got
        unreadable += bad
    warnings = []
    if unreadable:
        warnings.append(f"{unreadable} order item(s) skipped: no supplier, date, value or currency.")
    if len(lines) > sap_spend.MAX_LINES:
        raise SapError(f"SAP returned {len(lines)} order items, more than the {sap_spend.MAX_LINES} SCIRM reads "
                       "in one import. Nothing was imported.")
    if not net_amount:
        warnings.append("This SAP release has no item net value (NetAmount), so values are net price × quantity "
                        "÷ price unit; conditions such as discounts on the item may be missing.")
    return lines, warnings, today


async def check_connection(connection: Dict[str, Any], strict: Optional[bool] = None,
                           today: Optional[date] = None) -> Dict[str, Any]:
    """Check both services: reachable, authorised, with every field SCIRM reads, and
    accepting the exact query an import sends (filter, expand, select, order, count),
    for one record. A release that rejects any part of it fails here, not mid-import."""
    today = today or date.today()
    checks = []
    try:
        session = _Session(connection, strict)
    except SapError as exc:
        return {"ok": False, "checks": [{"service": "connection", "ok": False, "detail": str(exc)}]}
    async with session:
        for service in (BP_SERVICE, PO_SERVICE):
            name = service.rsplit("/", 1)[-1]
            try:
                found = await _check_metadata(session, service)
                entity, params, order_by = (_supplier_query() if service == BP_SERVICE
                                            else _order_query(today, NET_AMOUNT in found["A_PurchaseOrderItem"]))
                data = await session.json(service, f"/{entity}", _page_query(params, 1, 0, order_by, True))
                checks.append({"service": name, "ok": True, "detail": "readable", "records": data.get("__count")})
            except SapError as exc:
                checks.append({"service": name, "ok": False, "detail": str(exc)})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}

