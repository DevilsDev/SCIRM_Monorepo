"""
SCIRM Chat Agent
Natural language interface for querying supply chain risk data.
Uses LLM function-calling to route queries to existing API endpoints.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

import httpx
import structlog
from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.monitoring import setup_monitoring
from libs.common.security import setup_cors
from libs.common import llm as llm_client

logger = structlog.get_logger()

COORDINATOR_URL = os.getenv("COORDINATOR_SERVICE_URL", "http://localhost:8001")
RISK_SCORER_URL = os.getenv("RISK_SCORER_SERVICE_URL", "http://localhost:8006")

app = FastAPI(title="SCIRM Chat Agent", description="Natural language supply chain risk assistant", version="1.0.0")
setup_cors(app)
setup_monitoring(app, service_name="chat")

_http: httpx.AsyncClient = None


async def _get_client() -> httpx.AsyncClient:
    global _http
    if not _http:
        _http = httpx.AsyncClient(timeout=15.0)
    return _http


class ChatRequest(BaseModel):
    message: str
    context: Dict[str, Any] = {}


class ChatResponse(BaseModel):
    reply: str
    data: Dict[str, Any] = {}
    sources: list = []
    timestamp: str


# Intent patterns and their handlers
INTENTS = {
    "risk_summary": {"keywords": ["how many risks", "risk summary", "total risks", "risk overview", "dashboard"], "description": "Get risk count and severity breakdown"},
    "supplier_info": {"keywords": ["supplier", "suppliers", "vendor", "who supplies"], "description": "Look up supplier information"},
    "high_risk": {"keywords": ["high risk", "critical risk", "most dangerous", "biggest risk", "worst"], "description": "Find highest risk items"},
    "predictions": {"keywords": ["predict", "forecast", "next week", "disruption probability", "7 day"], "description": "Get disruption predictions"},
    "alerts": {"keywords": ["alerts", "warnings", "notifications", "active alerts"], "description": "Check active alerts"},
    "score_supplier": {"keywords": ["score", "rate", "assess", "evaluate", "risk profile"], "description": "Score a supplier's risk dimensions"},
    "recommendations": {"keywords": ["recommend", "suggestion", "what should", "mitigation", "action"], "description": "Get risk mitigation recommendations"},
    "events": {"keywords": ["event", "incident", "disruption", "typhoon", "earthquake", "breach"], "description": "Check risk events"},
}


def _classify_intent(message: str) -> str:
    msg_lower = message.lower()
    best_intent = "general"
    best_score = 0
    for intent, config in INTENTS.items():
        score = sum(1 for kw in config["keywords"] if kw in msg_lower)
        if score > best_score:
            best_score = score
            best_intent = intent
    return best_intent


async def _handle_risk_summary() -> tuple:
    client = await _get_client()
    resp = await client.get(f"{COORDINATOR_URL}/risks", params={"limit": 100})
    data = resp.json()
    risks = data.get("risks", [])
    total = data.get("total", 0)
    critical = len([r for r in risks if r.get("severity") == "critical"])
    high = len([r for r in risks if r.get("severity") == "high"])
    medium = len([r for r in risks if r.get("severity") == "medium"])
    low = len([r for r in risks if r.get("severity") == "low"])
    reply = f"There are **{total} active risks**: {critical} critical, {high} high, {medium} medium, {low} low."
    if high + critical > 0:
        reply += f" You have {high + critical} high/critical risks requiring immediate attention."
    return reply, {"total": total, "critical": critical, "high": high, "medium": medium, "low": low}


async def _handle_supplier_info() -> tuple:
    client = await _get_client()
    resp = await client.get(f"{COORDINATOR_URL}/suppliers")
    data = resp.json()
    suppliers = data.get("suppliers", [])
    lines = [f"**{len(suppliers)} suppliers** tracked:\n"]
    for s in suppliers[:10]:
        tier_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(s.get("risk_tier"), "⚪")
        lines.append(f"- {tier_emoji} **{s['name']}** ({s.get('country_code','')}) — Risk: {s.get('risk_score',0):.0f}/100 ({s.get('risk_tier','?')})")
    return "\n".join(lines), {"suppliers": suppliers}


async def _handle_high_risk() -> tuple:
    client = await _get_client()
    resp = await client.get(f"{COORDINATOR_URL}/risks", params={"severity": "high", "limit": 10})
    data = resp.json()
    risks = data.get("risks", [])
    if not risks:
        resp2 = await client.get(f"{COORDINATOR_URL}/risks", params={"severity": "critical", "limit": 10})
        risks = resp2.json().get("risks", [])
    if not risks:
        return "No high or critical risks found. Your supply chain looks healthy!", {}
    lines = [f"**{len(risks)} high-priority risks:**\n"]
    for r in risks[:5]:
        lines.append(f"- 🔴 **{r['title']}** — {r.get('risk_category','')} (impact: {r.get('impact_score',0):.1f}, probability: {r.get('probability',0):.0%})")
    return "\n".join(lines), {"risks": risks}


async def _handle_predictions() -> tuple:
    client = await _get_client()
    resp = await client.get(f"{COORDINATOR_URL}/predictions")
    data = resp.json()
    preds = data.get("predictions", [])
    if not preds:
        return "No predictions available yet. Run a risk assessment first to generate 7-day forecasts.", {}
    lines = ["**7-Day Disruption Predictions:**\n"]
    for p in preds:
        emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(p.get("severity"), "⚪")
        lines.append(f"- {emoji} **{p['category']}** — {p['predicted_disruption_probability']:.0%} disruption probability ({p['risk_count']} active risks)")
    return "\n".join(lines), {"predictions": preds}


async def _handle_alerts() -> tuple:
    client = await _get_client()
    resp = await client.get(f"{COORDINATOR_URL}/alerts")
    data = resp.json()
    alerts = data.get("alerts", [])
    active = [a for a in alerts if a.get("status") == "active"]
    if not active:
        return "No active alerts. All clear! ✅", {}
    lines = [f"**{len(active)} active alerts:**\n"]
    for a in active[:5]:
        lines.append(f"- ⚠️ **{a['title']}** ({a.get('severity','?')})")
    return "\n".join(lines), {"alerts": active}


async def _handle_events() -> tuple:
    client = await _get_client()
    resp = await client.get(f"{COORDINATOR_URL}/events")
    data = resp.json()
    events = data.get("events", [])
    if not events:
        return "No risk events recorded.", {}
    lines = [f"**{len(events)} risk events:**\n"]
    for e in events[:5]:
        lines.append(f"- ⚡ **{e['title']}** ({e.get('severity','?')}) — {e.get('affected_region','Global')}")
    return "\n".join(lines), {"events": events}


async def _handle_general(message: str) -> tuple:
    """Use LLM for free-form questions."""
    if llm_client.is_configured():
        try:
            prompt = f"""You are SCIRM, an AI supply chain risk management assistant. Answer this question:

"{message}"

Provide a helpful, concise answer about supply chain risk management. If you need specific data, suggest what the user should check in the platform (e.g., "Check the Suppliers page" or "Run a New Assessment").
Keep your answer under 100 words."""
            reply = await llm_client.generate(prompt, system="You are SCIRM, a helpful supply chain risk management AI assistant. Be concise and actionable.")
            return reply, {}
        except Exception:
            pass

    return "I can help you with: risk summaries, supplier info, high-risk items, predictions, alerts, events, and risk scoring. Try asking something like \"How many risks do we have?\" or \"Show me high-risk suppliers\".", {}


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "chat", "llm_configured": llm_client.is_configured()}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "chat"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a natural language query about supply chain risks."""
    intent = _classify_intent(request.message)
    logger.info("Chat query", message=request.message[:50], intent=intent)

    handlers = {
        "risk_summary": _handle_risk_summary,
        "supplier_info": _handle_supplier_info,
        "high_risk": _handle_high_risk,
        "predictions": _handle_predictions,
        "alerts": _handle_alerts,
        "events": _handle_events,
    }

    handler = handlers.get(intent)
    if handler:
        try:
            reply, data = await handler()
        except Exception as exc:
            logger.error("Chat handler failed", intent=intent, error=str(exc))
            reply = f"I tried to look that up but encountered an error. Try checking the {intent.replace('_', ' ')} page directly."
            data = {}
    else:
        reply, data = await _handle_general(request.message)

    return ChatResponse(
        reply=reply,
        data=data,
        sources=[intent],
        timestamp=datetime.utcnow().isoformat(),
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("CHAT_SERVICE_PORT", "8009"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
