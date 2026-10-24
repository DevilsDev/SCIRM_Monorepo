"""
Webhooks: signed HTTP POSTs to a tenant's endpoint when a new public record matches one
of its suppliers.

Events
- record.matched: a new public record names a supplier (FDA recall, shortage, warning
  letter, import alert). One event per recall event and supplier, listing every record.
- exposure.detected: a new disaster alert near one of the supplier's sites, or in its
  country when sites are unknown or the alert has no point (droughts).
- watchlist.matched: a new FDA or EMA record names a substance or product on the
  organization's regulatory watchlist (libs/intel/watchlist.py). One event per record,
  listing the terms it names.
- ping: sent by the "Send test" button.

Only records first seen after webhooks were set up for the organization are sent. An alert
that is later upgraded (for example GDACS Orange to Red) keeps its first-seen time, so it
does not produce a second event.

Delivery is at least once: receivers should ignore an event id they have already handled.
Each request is signed (see sign()); retries back off over about a day, then the delivery is
marked failed. The URL is checked like the SAP address (libs/common/outbound.py): outside
development HTTPS only, public addresses only, pinned to the checked address, no redirects
followed, short timeout, and only the status code of the answer is kept.
"""

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from libs.common import outbound
from libs.intel import matching, watchlist

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
STRICT = _ENVIRONMENT not in {"development", "dev", "local", "test"}

EVENT_TYPES = ("record.matched", "exposure.detected", "watchlist.matched")
MIN_CONFIDENCE = float(os.getenv("WEBHOOK_MIN_CONFIDENCE", "0.6"))  # as the supplier panel
# Seconds to wait before attempt n+1 (after n failures). Then the delivery is marked failed.
BACKOFF = (60, 300, 1800, 7200, 21600, 43200)
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_PAYLOAD_RECORDS = 25
# Longer than the longest ingestion transaction (see detect()).
OVERLAP_SECONDS = int(os.getenv("WEBHOOK_OVERLAP_SECONDS", "1800"))
# Deliveries claimed per pass, and how long a claim lasts: longer than a full batch can take
# (BATCH x 10 s timeout), so another replica never re-claims a delivery still being sent.
BATCH = 10
LEASE_SECONDS = 300

# Code-only hooks for tests: an httpx transport, and the DNS resolver.
transport_factory: Optional[Callable[[], httpx.AsyncBaseTransport]] = None
resolve: Callable[[str, int], List[str]] = outbound.system_resolve


class WebhookError(Exception):
    """A problem to show the person (bad URL, unreachable endpoint)."""


def validate_url(url: str, strict: Optional[bool] = None) -> str:
    strict = STRICT if strict is None else strict
    url = (url or "").strip()
    try:
        parts = urlsplit(url)
        parts.port
    except ValueError:
        raise WebhookError("The webhook URL is not valid.")
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise WebhookError("The webhook URL must start with https:// and name a host.")
    if strict and parts.scheme != "https":
        raise WebhookError("The webhook URL must use https://.")
    if parts.username or parts.password or "@" in parts.netloc:
        raise WebhookError("Do not put credentials in the webhook URL; verify the signature instead.")
    if parts.fragment:
        raise WebhookError("The webhook URL must not contain a fragment (#).")
    if len(url) > 500:
        raise WebhookError("The webhook URL is too long.")
    return url


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """HMAC-SHA256 over "<timestamp>.<body>", hex. Sent as SCIRM-Signature: t=<ts>,v1=<hex>."""
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify(secret: str, header: str, body: bytes, tolerance: int = 300, now: Optional[int] = None) -> bool:
    """What a receiver does (also used in tests): check the signature and reject old timestamps."""
    try:
        fields = dict(part.split("=", 1) for part in header.split(","))
        ts = int(fields["t"])
    except (ValueError, KeyError):
        return False
    if abs((now or int(time.time())) - ts) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, ts, body), fields.get("v1", ""))


def body_for(event: Dict[str, Any]) -> bytes:
    """The exact bytes sent and signed."""
    return json.dumps({"id": event["id"], "type": event["type"], "created_at": event["created_at"],
                       "data": event["payload"]}, sort_keys=True, separators=(",", ":"), default=str).encode()


def _record(signal: Dict[str, Any]) -> Dict[str, Any]:
    return {k: signal.get(k) for k in ("id", "source", "external_id", "signal_type", "title", "url", "severity",
                                       "country_codes", "published_at", "updated_at")}


def _supplier(s: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": str(s.get("id")), "name": s.get("name"), "country_code": s.get("country_code"),
            "sap_supplier_number": s.get("sap_supplier_number")}


def events_for(suppliers: List[Dict[str, Any]], signals: List[Dict[str, Any]]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """(type, dedupe key, payload) for new signals that match these suppliers, by the same
    rules as the supplier panel: incidents at MIN_CONFIDENCE or above, one per recall event;
    exposures near a site or, failing that, in the supplier's country."""
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    by_id = {str(s.get("id")): s for s in suppliers}
    for supplier_id, found in matching.match_all(suppliers, signals).items():
        supplier = _supplier(by_id[supplier_id])
        incidents = [m for m in found if m["kind"] == "incident" and m["confidence"] >= MIN_CONFIDENCE]
        for group in matching.group_events(incidents):
            top = group[0]
            key = matching.event_key(top["signal"])
            out.append(("record.matched", f"record.matched:{supplier_id}:{key}", {
                "supplier": supplier, "event_key": key,
                "match": {k: top[k] for k in ("match_type", "confidence", "matched_on")},
                "record": _record(top["signal"]),
                "records": [_record(m["signal"]) for m in group[:MAX_PAYLOAD_RECORDS]],
                "record_count": len(group)}))
        for m in (m for m in found if m["kind"] == "exposure"):
            sid = m["signal"].get("id")
            match = {k: m[k] for k in ("match_type", "confidence", "matched_on")}
            if m.get("site"):
                match["site"] = m["site"]
            out.append(("exposure.detected", f"exposure.detected:{supplier_id}:{sid}",
                        {"supplier": supplier, "match": match, "record": _record(m["signal"])}))
    return out


def watchlist_events(terms: List[str], signals: List[Dict[str, Any]]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """(type, dedupe key, payload) for new regulatory records that name a watched term."""
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    for signal in signals:
        named = watchlist.matching_terms(signal, terms)
        if named:
            out.append(("watchlist.matched", f"watchlist.matched:{signal.get('source')}:{signal.get('external_id')}",
                        {"terms": named, "record": _record(signal)}))
    return out


def next_attempt(attempts: int, now: datetime) -> Optional[datetime]:
    """When to retry after `attempts` failed attempts, or None to give up."""
    return now + timedelta(seconds=BACKOFF[attempts - 1]) if attempts <= len(BACKOFF) else None


async def deliver(url: str, secret: str, event: Dict[str, Any], strict: Optional[bool] = None) -> Dict[str, Any]:
    """POST one event. Returns {"ok", "status_code", "error"}; never raises for the endpoint's
    behaviour. A 2xx is success; redirects are not followed and count as failures."""
    strict = STRICT if strict is None else strict
    try:
        url = validate_url(url, strict)
        # DNS resolution blocks; keep it off the event loop that also serves the API.
        target, sni = await asyncio.to_thread(outbound.pin, url, strict, resolve)
    except WebhookError as exc:
        return {"ok": False, "status_code": None, "error": str(exc)}
    except outbound.OutboundError as exc:
        reason = "could not be found (DNS)" if exc.kind == "dns" else "is not a public address"
        return {"ok": False, "status_code": None, "error": f"The host {exc.host} {reason}."}
    body = body_for(event)
    ts = int(time.time())
    headers = {"Content-Type": "application/json", "User-Agent": "SCIRM-Webhooks/1",
               "SCIRM-Event-Id": str(event["id"]), "SCIRM-Event-Type": event["type"],
               "SCIRM-Signature": f"t={ts},v1={sign(secret, ts, body)}"}
    if sni:
        headers["Host"] = urlsplit(url).netloc
    kwargs: Dict[str, Any] = {"timeout": TIMEOUT, "follow_redirects": False}
    if transport_factory is not None:
        kwargs["transport"] = transport_factory()
    try:
        async with httpx.AsyncClient(**kwargs) as client:
            async with client.stream("POST", target, content=body, headers=headers,
                                     extensions={"sni_hostname": sni} if sni else {}) as response:
                status = response.status_code  # the body is never read or stored
    except httpx.TimeoutException:
        return {"ok": False, "status_code": None, "error": "The endpoint did not answer within 10 seconds."}
    except httpx.HTTPError as exc:
        return {"ok": False, "status_code": None, "error": f"Could not connect ({type(exc).__name__})."}
    if 200 <= status < 300:
        return {"ok": True, "status_code": status, "error": None}
    return {"ok": False, "status_code": status, "error": f"The endpoint answered HTTP {status}."}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def detect(store: Any, org: str) -> int:
    """Turn public records first seen since the organization's watermark into events.
    The first run only sets the watermark. Returns the number of new events."""
    until = await store.db_now()  # database time: first_seen_at is set by the database
    state = await store.get_watermark(org)
    if state is None:
        await store.set_watermark(org, until)
        return 0
    # first_seen_at is the start time of the ingestion transaction, which commits later (a
    # whole source in one transaction). Re-reading the last OVERLAP_SECONDS catches rows that
    # committed after the previous run read past their timestamp; the dedupe key makes the
    # overlap harmless. Never before the first run, so the archive is not replayed.
    after = max(datetime.fromisoformat(state["watermark"]) - timedelta(seconds=OVERLAP_SECONDS),
                datetime.fromisoformat(state["started_at"])).isoformat()
    suppliers, _ = await store.list_suppliers(org, limit=None)
    suppliers = [s for s in suppliers if s.get("is_active", True)]
    created = 0
    if suppliers:
        index = matching.supplier_index(suppliers)
        signals = await store.new_signal_candidates(index["keys"], index["countries"], after, until)
        if signals:
            created = len(await store.record_events(org, events_for(suppliers, signals)))
    terms = [item["term"] for item in await store.list_watchlist(org)]
    if terms:
        signals = await store.regulatory_candidates(terms, first_seen_after=after, first_seen_until=until)
        found = watchlist_events(terms, signals)
        if found:
            created += len(await store.record_events(org, found))
    await store.set_watermark(org, until)
    return created


async def deliver_due(store: Any, org: str, only_events: Optional[List[str]] = None,
                      limit: int = BATCH) -> List[Dict[str, Any]]:
    """Send this organization's due deliveries (paused webhooks are skipped); record each
    outcome and schedule retries."""
    results = []
    for job in await store.claim_deliveries(org, limit=limit, lease_seconds=LEASE_SECONDS, only=only_events):
        result = await deliver(job["url"], job["secret"], job["event"])
        retry_at = None if result["ok"] else next_attempt(job["attempts"], utcnow())
        await store.finish_delivery(org, job["delivery_id"], result, retry_at)
        results.append({**result, "delivery_id": job["delivery_id"], "event_id": job["event"]["id"],
                        "webhook_id": job["webhook_id"], "attempts": job["attempts"]})
    return results
