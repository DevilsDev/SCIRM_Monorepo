"""
Scheduled reports: a supplier risk digest emailed to an organization's members.

The digest covers the period since the previous run (or one day, week or month for the
first): new public records naming the organization's suppliers (record.matched) and new
disaster exposures (exposure.detected), as recorded in webhook_events by the webhook
detector. Each record links to its source; the email links back to SCIRM when
PUBLIC_APP_URL is set.

Email goes out over SMTP (SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM,
SMTP_STARTTLS). Without SMTP_HOST nothing is sent and the schedule shows why. Recipients
must be active members of the organization, checked when saved and again when sent, so a
schedule cannot be used to send supplier data outside the organization.
"""

import asyncio
import html
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

FREQUENCIES = ("daily", "weekly", "monthly")
PERIOD = {"daily": timedelta(days=1), "weekly": timedelta(days=7), "monthly": timedelta(days=31)}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_ROWS = 200
LEASE = timedelta(minutes=10)


def smtp_config() -> Optional[Dict[str, Any]]:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return None
    return {"host": host, "port": int(os.getenv("SMTP_PORT", "587")), "username": os.getenv("SMTP_USERNAME", ""),
            "password": os.getenv("SMTP_PASSWORD", ""), "sender": os.getenv("SMTP_FROM", "SCIRM <no-reply@localhost>"),
            "starttls": os.getenv("SMTP_STARTTLS", "true").lower() == "true"}


def next_run(frequency: str, hour_utc: int, weekday: Optional[int], after: datetime) -> datetime:
    """The first scheduled time strictly after `after` (UTC): daily at hour_utc, weekly on
    weekday (0 = Monday) at hour_utc, monthly on the 1st at hour_utc."""
    after = after.astimezone(timezone.utc)
    if frequency == "daily":
        candidate = after.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        return candidate if candidate > after else candidate + timedelta(days=1)
    if frequency == "weekly":
        candidate = after.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        candidate += timedelta(days=(int(weekday or 0) - candidate.weekday()) % 7)
        return candidate if candidate > after else candidate + timedelta(days=7)
    if frequency == "monthly":
        candidate = after.replace(day=1, hour=hour_utc, minute=0, second=0, microsecond=0)
        if candidate > after:
            return candidate
        year, month = (candidate.year + 1, 1) if candidate.month == 12 else (candidate.year, candidate.month + 1)
        return candidate.replace(year=year, month=month)
    raise ValueError(f"unknown frequency {frequency!r}")


def describe(frequency: str, hour_utc: int, weekday: Optional[int]) -> str:
    when = f"{hour_utc:02d}:00 UTC"
    if frequency == "daily":
        return f"Every day at {when}"
    if frequency == "weekly":
        return f"Every {WEEKDAYS[int(weekday or 0)]} at {when}"
    return f"On the 1st of every month at {when}"


def _row(event: Dict[str, Any]) -> Dict[str, Any]:
    data = event.get("payload") or {}
    record, supplier, match = data.get("record") or {}, data.get("supplier") or {}, data.get("match") or {}
    where = ""
    if match.get("site"):
        site = match["site"]
        where = f"{site.get('distance_km', '?')} km from {site.get('site') or 'a site'}"
    elif match.get("match_type") == "country_exposure":
        where = f"in {match.get('matched_on')}"
    terms = data.get("terms") or []
    label = supplier.get("name") or (f"Watching {', '.join(terms)}" if terms else "")
    return {"type": event["type"], "supplier": label, "title": record.get("title") or "",
            "source": record.get("source") or "", "severity": record.get("severity") or "",
            "url": record.get("url") or "", "published": (record.get("published_at") or "")[:10],
            "count": data.get("record_count") or 1, "where": where}


def build_digest(org_name: str, events: List[Dict[str, Any]], since: datetime, until: datetime,
                 app_url: str = "") -> Tuple[str, str, str]:
    """(subject, plain text, HTML) of the supplier risk digest."""
    rows = [_row(e) for e in events if e["type"] in ("record.matched", "exposure.detected", "watchlist.matched")]
    records = [r for r in rows if r["type"] == "record.matched"]
    exposures = [r for r in rows if r["type"] == "exposure.detected"]
    watched = [r for r in rows if r["type"] == "watchlist.matched"]
    sections = (("New public records naming your suppliers", records), ("New disaster exposures", exposures),
                ("Regulatory watch: FDA and EMA records naming substances or products you watch", watched))
    period = f"{since.astimezone(timezone.utc):%Y-%m-%d %H:%M} to {until.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC"
    if rows:
        subject = (f"SCIRM digest for {org_name}: {len(records)} new record(s) naming your suppliers, "
                   f"{len(exposures)} disaster exposure(s)"
                   + (f", {len(watched)} regulatory watch match(es)" if watched else ""))
    else:
        subject = f"SCIRM digest for {org_name}: nothing new"
    text = [f"Supplier risk digest for {org_name}", period, ""]
    if not rows:
        text.append("No new public records named your suppliers, and no new disaster alerts were near them.")
    for title, group in sections:
        if group:
            text += [f"{title} ({len(group)})", ""]
            for r in group[:MAX_ROWS]:
                extra = f" ({r['count']} records)" if r["count"] > 1 else ""
                text.append(f"- {r['supplier']}: {r['title']}{extra} [{r['severity']}] {r['where']} {r['url']}".rstrip())
            if len(group) > MAX_ROWS:
                text.append(f"... and {len(group) - MAX_ROWS} more in SCIRM.")
            text.append("")
    text += ["These are public records matched by name, and alerts matched by location. They are not findings "
             "about your suppliers; check the source record.", ""]
    if app_url:
        text.append(f"Open SCIRM: {app_url}/suppliers")

    e = html.escape

    cell = "<td style='padding:4px 8px'>{}</td>"

    def record_cell(r: Dict[str, Any]) -> str:
        title = e(r["title"])
        if r["url"]:
            title = f"<a href=\"{e(r['url'])}\">{title}</a>"
        if r["count"] > 1:
            title += f" ({r['count']} records)"
        return title

    def table(group: List[Dict[str, Any]]) -> str:
        head = "".join(f"<th style='padding:4px 8px'>{h}</th>"
                       for h in ("Supplier", "Record", "Severity", "Where", "Published"))
        body = "".join("<tr>" + "".join(cell.format(v) for v in (
            e(r["supplier"]), record_cell(r), e(r["severity"]), e(r["where"]), e(r["published"]))) + "</tr>"
            for r in group[:MAX_ROWS])
        more = f"<p>... and {len(group) - MAX_ROWS} more in SCIRM.</p>" if len(group) > MAX_ROWS else ""
        return (f"<table style='border-collapse:collapse;font-size:13px'><tr style='text-align:left'>{head}</tr>"
                f"{body}</table>{more}")

    parts = [f"<h2 style='font-family:sans-serif'>Supplier risk digest for {e(org_name)}</h2>",
             f"<p style='font-family:sans-serif;color:#555'>{e(period)}</p>"]
    if not rows:
        parts.append("<p style='font-family:sans-serif'>No new public records named your suppliers, and no new "
                     "disaster alerts were near them.</p>")
    for title, group in sections:
        if group:
            parts.append(f"<h3 style='font-family:sans-serif'>{e(title)} ({len(group)})</h3>{table(group)}")
    parts.append("<p style='font-family:sans-serif;color:#777;font-size:12px'>These are public records matched by "
                 "name, and alerts matched by location. They are not findings about your suppliers; check the source "
                 "record.</p>")
    if app_url:
        parts.append(f"<p style='font-family:sans-serif'><a href='{e(app_url)}/suppliers'>Open SCIRM</a></p>")
    return subject, "\n".join(text), "<div>" + "".join(parts) + "</div>"


def _send_sync(config: Dict[str, Any], recipients: List[str], subject: str, text: str, body_html: str) -> None:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = config["sender"], ", ".join(recipients), subject
    message.set_content(text)
    message.add_alternative(body_html, subtype="html")
    with smtplib.SMTP(config["host"], config["port"], timeout=30) as smtp:
        if config["starttls"]:
            smtp.starttls(context=ssl.create_default_context())
        if config["username"]:
            smtp.login(config["username"], config["password"])
        smtp.send_message(message)


async def send_email(recipients: List[str], subject: str, text: str, body_html: str) -> None:
    config = smtp_config()
    if config is None:
        raise RuntimeError("Email is not configured (SMTP_HOST).")
    await asyncio.to_thread(_send_sync, config, recipients, subject, text, body_html)


async def run_due(store: Any, org: str, app_url: str = "") -> List[Dict[str, Any]]:
    """Send this organization's due reports. Each claimed schedule has already been moved to
    a short lease, so another replica skips it; afterwards it is set to its next run."""
    results = []
    for schedule in await store.claim_due_reports(org, lease_seconds=int(LEASE.total_seconds())):
        # Database time: events are stamped by the database, and the window is (since, now].
        now = datetime.fromisoformat(await store.db_now())
        last = schedule.get("last_run_at")
        since = datetime.fromisoformat(last) if last else now - PERIOD[schedule["frequency"]]
        status: Dict[str, Any]
        try:
            members = {m["email"].lower() for m in await store.list_members(org) if m.get("is_active")}
            recipients = [r for r in schedule["recipients"] if r.lower() in members]
            if not recipients:
                raise RuntimeError("None of the recipients is an active member of the organization any more.")
            events = await store.list_events(org, since.isoformat(), now.isoformat())
            if schedule.get("skip_empty") and not events:
                status = {"ok": True, "sent": False, "events": 0, "detail": "Nothing new; not sent (skip empty)."}
            else:
                subject, text, body_html = build_digest(await store.organization_name(org), events, since, now, app_url)
                await send_email(recipients, subject, text, body_html)
                status = {"ok": True, "sent": True, "events": len(events), "recipients": len(recipients)}
        except Exception as exc:  # recorded on the schedule; the next run still happens
            status = {"ok": False, "sent": False, "error": str(exc)[:300] or type(exc).__name__}
        nxt = next_run(schedule["frequency"], schedule["hour_utc"], schedule.get("weekday"), now)
        await store.finish_report(org, schedule["id"], nxt.isoformat(), now.isoformat() if status["ok"] else None,
                                  {**status, "at": now.isoformat()})
        results.append({**status, "schedule_id": schedule["id"]})
    return results
