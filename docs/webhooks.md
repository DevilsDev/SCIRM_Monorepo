# Webhooks

SCIRM can notify another system when a **new public record matches one of your
suppliers**. It sends a signed HTTPS `POST` to an endpoint you choose.

## Events

| Type | Sent when |
|---|---|
| `record.matched` | A new FDA recall, shortage, warning letter or import alert names a supplier, by the same name rules as the supplier panel (confidence 0.6 or more). One event per recall event and supplier, listing every record it covers. |
| `exposure.detected` | A new GDACS disaster alert is near one of the supplier's sites (within the alert radius), or is in its country when its sites are unknown or the alert has no point (droughts). |
| `ping` | You pressed **Send test**. |

Only records **first seen after the endpoint's organization started using webhooks** are
sent, so adding an endpoint does not replay the archive. An alert that is later upgraded
(for example GDACS Orange to Red) keeps its first-seen time, so it does not produce a
second event. SCIRM checks for new records every 5 minutes (`WEBHOOK_DETECT_SECONDS`), and
public sources are ingested hourly.

## Setting up

An administrator adds endpoints in **Administration → Integrations → Webhooks**: a URL, an optional
description, and the event types to send.
- **Secret shown once.** The signing secret (`whsec_…`) is shown only when the endpoint is
  added. SCIRM stores it encrypted (AES-256-GCM, `MFA_ENCRYPTION_KEY`).
- **Send test** delivers a `ping` at once and shows the answer.
- **History** lists recent deliveries.
- **Pause** stops deliveries without deleting the endpoint.

Adding and deleting endpoints are recorded in the [audit log](audit-log.md).

Outside development the URL must be `https://` and resolve to a public address. SCIRM
connects to the address it checked (keeping the name for TLS), never follows redirects,
waits at most 10 seconds, and keeps only the status code of the answer, never its body.
The same guard applies to the SAP connection.

## The request

```http
POST /your/path HTTP/1.1
Content-Type: application/json
User-Agent: SCIRM-Webhooks/1
SCIRM-Event-Id: 6f1c…
SCIRM-Event-Type: record.matched
SCIRM-Signature: t=1792697571,v1=a9f7146…

{"created_at":"2026-10-23T08:32:51+00:00","data":{…},"id":"6f1c…","type":"record.matched"}
```

`data` for `record.matched`:
- `supplier`: `id`, `name`, `country_code`, `sap_supplier_number`
- `match`: `match_type`, `confidence`, `matched_on`
- `record`: the most severe record (`source`, `external_id`, `title`, `url`, `severity`,
  `published_at`, …)
- `records`: up to 25 records of the same event
- `record_count`

`exposure.detected` has `supplier`, `match` (with `site` and the distance for site
matches) and `record`.

## Verifying the signature

`v1` is the HMAC-SHA256, in hex, of `"<t>.<raw request body>"` with your signing secret.
Reject requests whose `t` is more than 5 minutes from your clock, to stop replays.

```python
import hashlib, hmac, time

def verify(secret: str, header: str, body: bytes, tolerance: int = 300) -> bool:
    fields = dict(part.split("=", 1) for part in header.split(","))
    ts = int(fields["t"])
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, fields["v1"])
```

Use the raw body exactly as received, before any JSON parsing.

## Delivery

Answer with any `2xx` status within 10 seconds. Anything else (including a redirect or a
timeout) is retried after 1 minute, 5 minutes, 30 minutes, 2 hours, 6 hours and 12 hours;
after that the delivery is marked failed.

Delivery is **at least once**: an event can arrive twice (for example after a timeout), so
ignore an `SCIRM-Event-Id` you have already handled. Events can arrive out of order.

## Operations

The coordinator detects and delivers. It needs `MFA_ENCRYPTION_KEY` (it already does, for
SAP) and outbound HTTPS.

| Variable | Default | |
|---|---|---|
| `WEBHOOKS_ENABLED` | `true` | turn the detector and sender off |
| `WEBHOOK_DETECT_SECONDS` | `300` | how often new records are checked |
| `WEBHOOK_TICK_SECONDS` | `30` | how often due deliveries are sent |
| `WEBHOOK_MIN_CONFIDENCE` | `0.6` | name-match threshold for `record.matched` |

Several coordinator replicas are safe:
- Events are unique per organization and key, so an event is never created twice.
- Deliveries are claimed with `FOR UPDATE SKIP LOCKED` and a short lease, so two
  replicas never send the same delivery.
