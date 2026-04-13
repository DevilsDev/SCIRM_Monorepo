"""
SCIRM Alerting Integration
PagerDuty, Slack, and webhook-based alert notifications.
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger()

PAGERDUTY_ROUTING_KEY = os.getenv("PAGERDUTY_ROUTING_KEY", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")


async def send_pagerduty_alert(
    severity: str,
    summary: str,
    source: str = "SCIRM",
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send an alert to PagerDuty Events API v2."""
    if not PAGERDUTY_ROUTING_KEY:
        logger.debug("PagerDuty not configured, skipping alert")
        return False

    pd_severity = {"critical": "critical", "high": "error", "medium": "warning", "low": "info"}.get(severity, "warning")

    payload = {
        "routing_key": PAGERDUTY_ROUTING_KEY,
        "event_action": "trigger",
        "payload": {
            "summary": summary,
            "severity": pd_severity,
            "source": source,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "custom_details": details or {},
            "component": "scirm-risk-engine",
            "group": "supply-chain-risks",
            "class": f"risk_{severity}",
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info("PagerDuty alert sent", severity=severity, summary=summary[:50])
            return True
    except Exception as exc:
        logger.error("PagerDuty alert failed", error=str(exc))
        return False


async def send_slack_alert(
    severity: str,
    title: str,
    description: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send an alert to Slack via webhook."""
    if not SLACK_WEBHOOK_URL:
        logger.debug("Slack not configured, skipping alert")
        return False

    color = {"critical": "#ef4444", "high": "#f97316", "medium": "#eab308", "low": "#22c55e"}.get(severity, "#94a3b8")

    payload = {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"🚨 {severity.upper()}: {title}"},
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": description or "No description provided."},
                    },
                    {
                        "type": "context",
                        "elements": [
                            {"type": "mrkdwn", "text": f"*Source:* SCIRM Risk Engine | *Time:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"},
                        ],
                    },
                ],
            }
        ],
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SLACK_WEBHOOK_URL, json=payload, timeout=10.0)
            resp.raise_for_status()
            logger.info("Slack alert sent", severity=severity, title=title[:50])
            return True
    except Exception as exc:
        logger.error("Slack alert failed", error=str(exc))
        return False


async def send_webhook_alert(
    severity: str,
    title: str,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send an alert to a generic webhook URL."""
    if not ALERT_WEBHOOK_URL:
        return False

    payload = {
        "event": "risk_alert",
        "severity": severity,
        "title": title,
        "details": details or {},
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "scirm",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(ALERT_WEBHOOK_URL, json=payload, timeout=10.0)
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.error("Webhook alert failed", error=str(exc))
        return False


async def dispatch_alert(severity: str, title: str, description: str = "", details: Optional[Dict[str, Any]] = None):
    """Send alert to all configured channels."""
    results = {
        "pagerduty": await send_pagerduty_alert(severity, title, details=details),
        "slack": await send_slack_alert(severity, title, description, details),
        "webhook": await send_webhook_alert(severity, title, details),
    }
    logger.info("Alert dispatched", severity=severity, title=title[:50], channels=results)
    return results
