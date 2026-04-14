"""
SCIRM Autonomous Procurement Agent
Monitors supplier risk, identifies alternatives, and proposes/executes procurement actions.
Operates in 3 modes: advisory, semi-autonomous, autonomous.
"""

import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.monitoring import setup_monitoring
from libs.common.security import setup_cors
from libs.common import llm as llm_client

logger = structlog.get_logger()

app = FastAPI(title="SCIRM Procurement Agent", description="Autonomous procurement and sourcing", version="1.0.0")
setup_cors(app)
setup_monitoring(app, service_name="procurement")

PROCUREMENT_MODE = os.getenv("PROCUREMENT_MODE", "advisory")  # advisory | semi_auto | auto
RISK_THRESHOLD = float(os.getenv("PROCUREMENT_RISK_THRESHOLD", "65"))

# In-memory actions store
_actions: List[Dict[str, Any]] = []

# Alternative supplier database
ALTERNATIVE_SUPPLIERS = {
    "Supplier Alpha": [
        {"name": "AlphaAlt Pharma Inc", "country": "US", "lead_time": 18, "cost_premium": 0.05, "risk_score": 25},
        {"name": "Nordic API Solutions", "country": "SE", "lead_time": 25, "cost_premium": 0.12, "risk_score": 20},
    ],
    "Supplier Beta": [
        {"name": "Swiss Excipient AG", "country": "CH", "lead_time": 20, "cost_premium": 0.08, "risk_score": 30},
    ],
    "Supplier Gamma": [
        {"name": "Korea Pack Corp", "country": "KR", "lead_time": 28, "cost_premium": 0.15, "risk_score": 35},
        {"name": "India Packaging Ltd", "country": "IN", "lead_time": 32, "cost_premium": -0.10, "risk_score": 45},
    ],
    "Supplier Delta": [
        {"name": "Taiwan Sensor Tech", "country": "TW", "lead_time": 12, "cost_premium": 0.03, "risk_score": 22},
        {"name": "Silicon Valley Sensors", "country": "US", "lead_time": 8, "cost_premium": 0.25, "risk_score": 15},
        {"name": "Munich Electronics GmbH", "country": "DE", "lead_time": 15, "cost_premium": 0.18, "risk_score": 18},
    ],
    "Supplier Epsilon": [
        {"name": "BioCompat Materials UK", "country": "GB", "lead_time": 22, "cost_premium": 0.10, "risk_score": 28},
        {"name": "Canadian BioMat Inc", "country": "CA", "lead_time": 15, "cost_premium": 0.07, "risk_score": 20},
    ],
}


class EvaluateRequest(BaseModel):
    suppliers: List[Dict[str, Any]]
    risk_threshold: float = 65.0


class ActionRequest(BaseModel):
    action_id: str
    decision: str  # approve | reject


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "procurement", "mode": PROCUREMENT_MODE, "threshold": RISK_THRESHOLD}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "procurement"}


@app.post("/evaluate")
async def evaluate_suppliers(request: EvaluateRequest):
    """Evaluate suppliers and generate procurement actions for those exceeding risk threshold."""
    new_actions = []
    threshold = request.risk_threshold or RISK_THRESHOLD

    for supplier in request.suppliers:
        risk = supplier.get("risk_score", 50)
        name = supplier.get("name", "Unknown")

        if risk < threshold:
            continue

        # Find alternatives
        alternatives = ALTERNATIVE_SUPPLIERS.get(name, [])

        if not alternatives:
            action = {
                "id": str(uuid.uuid4()),
                "action_type": "qualify_new_supplier",
                "title": f"Qualify new supplier to replace {name}",
                "description": f"{name} has risk score {risk:.0f} (threshold: {threshold:.0f}) with no known alternatives. Initiate supplier qualification process.",
                "status": "proposed",
                "current_supplier_name": name,
                "current_supplier_risk": risk,
                "proposed_supplier_name": None,
                "alternatives_count": 0,
                "estimated_savings": 0,
                "risk_reduction": 0,
                "requires_approval": True,
                "mode": PROCUREMENT_MODE,
                "created_at": datetime.utcnow().isoformat(),
            }
        else:
            # Pick best alternative (lowest risk + reasonable cost)
            best = min(alternatives, key=lambda a: a["risk_score"] + a.get("cost_premium", 0) * 100)
            risk_reduction = risk - best["risk_score"]

            if PROCUREMENT_MODE == "auto" and risk_reduction > 20:
                status = "executing"
            elif PROCUREMENT_MODE == "semi_auto":
                status = "proposed"
            else:
                status = "proposed"

            action = {
                "id": str(uuid.uuid4()),
                "action_type": "source_alternative",
                "title": f"Switch from {name} to {best['name']}",
                "description": f"Risk reduction: {risk:.0f} → {best['risk_score']:.0f} ({risk_reduction:.0f} points). "
                               f"Cost premium: {best['cost_premium']:+.0%}. Lead time: {best['lead_time']}d.",
                "status": status,
                "current_supplier_name": name,
                "current_supplier_risk": risk,
                "proposed_supplier_name": best["name"],
                "proposed_supplier_country": best["country"],
                "proposed_supplier_risk": best["risk_score"],
                "alternatives_count": len(alternatives),
                "all_alternatives": alternatives,
                "estimated_savings": round(-best.get("cost_premium", 0) * 100000, 2),
                "risk_reduction": round(risk_reduction, 1),
                "requires_approval": PROCUREMENT_MODE != "auto",
                "mode": PROCUREMENT_MODE,
                "created_at": datetime.utcnow().isoformat(),
            }

        new_actions.append(action)
        _actions.append(action)

    return {
        "actions": new_actions,
        "total_proposed": len(new_actions),
        "mode": PROCUREMENT_MODE,
        "threshold": threshold,
    }


@app.get("/actions")
async def list_actions(status: str = None):
    """List all procurement actions."""
    actions = _actions
    if status:
        actions = [a for a in actions if a.get("status") == status]
    return {"actions": actions, "total": len(actions)}


@app.post("/actions/{action_id}/decide")
async def decide_action(action_id: str, request: ActionRequest):
    """Approve or reject a procurement action."""
    for action in _actions:
        if action["id"] == action_id:
            if request.decision == "approve":
                action["status"] = "approved"
                action["approved_at"] = datetime.utcnow().isoformat()
            elif request.decision == "reject":
                action["status"] = "rejected"
            return action
    raise HTTPException(status_code=404, detail="Action not found")


@app.get("/alternatives/{supplier_name}")
async def get_alternatives(supplier_name: str):
    """Get alternative suppliers for a given supplier."""
    alternatives = ALTERNATIVE_SUPPLIERS.get(supplier_name, [])
    return {"supplier": supplier_name, "alternatives": alternatives, "total": len(alternatives)}


@app.get("/mode")
async def get_mode():
    """Get current procurement automation mode."""
    return {"mode": PROCUREMENT_MODE, "risk_threshold": RISK_THRESHOLD, "options": ["advisory", "semi_auto", "auto"]}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PROCUREMENT_SERVICE_PORT", "8011"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
