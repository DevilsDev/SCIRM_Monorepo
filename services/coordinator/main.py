"""
SCIRM Coordinator Agent
Meta-agent that orchestrates the multi-agent swarm workflow:
  Planner (CAG) → Researcher (RAG) → Executor → Reviewer
"""

import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncio

import httpx
import structlog
from fastapi import FastAPI, HTTPException, status

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.models import (
    AssessmentStatus,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
)
from libs.common.monitoring import setup_monitoring, track_agent_task
from libs.common.security import setup_cors

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PLANNER_URL = os.getenv("PLANNER_SERVICE_URL", "http://localhost:8002")
RESEARCHER_URL = os.getenv("RESEARCHER_SERVICE_URL", "http://localhost:8003")
EXECUTOR_URL = os.getenv("EXECUTOR_SERVICE_URL", "http://localhost:8004")
REVIEWER_URL = os.getenv("REVIEWER_SERVICE_URL", "http://localhost:8005")
AGENT_TIMEOUT = float(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))
AUTO_REFRESH_INTERVAL = int(os.getenv("AUTO_REFRESH_INTERVAL_MINUTES", "15"))
AUTO_REFRESH_ENABLED = os.getenv("AUTO_REFRESH_ENABLED", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logger = structlog.get_logger()

# In-memory task store — production would use Redis / DB
_tasks: Dict[str, Dict[str, Any]] = {}

# Shared HTTP client
_http_client: Optional[httpx.AsyncClient] = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(AGENT_TIMEOUT, connect=5.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
    )
    logger.info("Coordinator agent started", planner=PLANNER_URL, executor=EXECUTOR_URL, reviewer=REVIEWER_URL)

    # Start background auto-refresh task
    refresh_task = None
    if AUTO_REFRESH_ENABLED:
        refresh_task = asyncio.create_task(_auto_refresh_loop())
        logger.info("Auto-refresh enabled", interval_minutes=AUTO_REFRESH_INTERVAL)

    yield

    if refresh_task:
        refresh_task.cancel()
    await _http_client.aclose()
    logger.info("Coordinator agent stopped")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SCIRM Coordinator Agent",
    description="Meta-agent orchestrating the SCIRM multi-agent swarm",
    version="1.0.0",
    lifespan=lifespan,
)

setup_cors(app)
setup_monitoring(app, service_name="coordinator")


# ---------------------------------------------------------------------------
# Helper: call a downstream agent
# ---------------------------------------------------------------------------

async def _auto_refresh_loop():
    """Background task: re-assess all known entities every N minutes."""
    await asyncio.sleep(10)  # Wait for services to be ready
    while True:
        try:
            await asyncio.sleep(AUTO_REFRESH_INTERVAL * 60)
            logger.info("Auto-refresh: starting scheduled re-assessment")

            # Collect unique entities from previous assessments
            all_entities = []
            seen_ids = set()
            for task in _tasks.values():
                if task.get("status") == "completed" and task.get("request"):
                    for entity in task["request"].get("entities", []):
                        eid = entity.get("id", "")
                        if eid and eid not in seen_ids:
                            all_entities.append(entity)
                            seen_ids.add(eid)

            if not all_entities:
                logger.info("Auto-refresh: no entities to re-assess, skipping")
                continue

            # Run a fresh assessment with all known entities
            request = RiskAssessmentRequest(
                entities=[
                    {"id": e.get("id", ""), "name": e.get("name", ""), "type": e.get("type", ""), "location": e.get("location")}
                    for e in all_entities[:20]  # Cap at 20 entities per refresh
                ],
                assessment_type="refresh",
                context={"organization_id": "a0000000-0000-0000-0000-000000000001"},
            )

            task_id = f"refresh-{uuid.uuid4().hex[:8]}"
            _tasks[task_id] = {
                "status": "processing",
                "started_at": datetime.utcnow().isoformat(),
                "request": request.model_dump(mode="json"),
            }

            result = await _run_pipeline(task_id, request)
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
            _tasks[task_id]["result"] = result.model_dump(mode="json")

            logger.info(
                "Auto-refresh: completed",
                task_id=task_id,
                risks=len(result.risks),
                recommendations=len(result.recommendations),
            )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Auto-refresh failed", error=str(exc))
            await asyncio.sleep(60)  # Wait 1 min before retrying on error


async def _call_agent(
    service_name: str,
    url: str,
    endpoint: str,
    payload: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Call a downstream agent and return its JSON response."""
    full_url = f"{url}{endpoint}"
    step_start = time.time()

    try:
        logger.info("Calling agent", agent=service_name, url=full_url, task_id=task_id)
        resp = await _http_client.post(full_url, json=payload)
        resp.raise_for_status()
        result = resp.json()
        duration_ms = (time.time() - step_start) * 1000
        logger.info(
            "Agent responded",
            agent=service_name,
            status=resp.status_code,
            duration_ms=round(duration_ms, 1),
            task_id=task_id,
        )
        return result

    except httpx.TimeoutException:
        logger.error("Agent timeout", agent=service_name, url=full_url, task_id=task_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"{service_name} agent timed out after {AGENT_TIMEOUT}s",
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Agent error",
            agent=service_name,
            status=exc.response.status_code,
            body=exc.response.text[:500],
            task_id=task_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{service_name} agent returned {exc.response.status_code}",
        )
    except httpx.ConnectError:
        logger.warning("Agent unreachable", agent=service_name, url=full_url, task_id=task_id)
        return {}  # graceful degradation — workflow continues without this agent


# ---------------------------------------------------------------------------
# Orchestration pipeline
# ---------------------------------------------------------------------------

@track_agent_task("coordinator", "risk_assessment")
async def _run_pipeline(task_id: str, request: RiskAssessmentRequest) -> RiskAssessmentResponse:
    """Execute the full agent pipeline: Planner → Researcher → Executor → Reviewer."""
    reasoning_trail = []
    request_dict = request.model_dump(mode="json")

    # ── Step 1: Planner (CAG) ─────────────────────────────────────────
    planner_result = await _call_agent(
        "planner", PLANNER_URL, "/analyze-context",
        {"request": request_dict},
        task_id,
    )
    reasoning_trail.append({
        "agent": "planner",
        "step": "context_analysis",
        "reasoning": planner_result.get("reasoning", ""),
        "output": planner_result.get("context_summary", ""),
        "confidence": planner_result.get("confidence_score", 0),
        "data_sources": ["organizational_profile", "industry_requirements"],
    })

    # ── Step 2: Researcher (RAG) — optional, may not be deployed yet ─
    research_data: Dict[str, Any] = {}
    researcher_result = await _call_agent(
        "researcher", RESEARCHER_URL, "/research",
        {
            "query": f"supply chain risks for {request.assessment_type or 'comprehensive'} assessment",
            "data_sources": ["weather", "logistics", "news", "regulatory"],
            "entities": request_dict.get("entities", []),
            "context": planner_result,
        },
        task_id,
    )
    if researcher_result:
        research_data = researcher_result
        reasoning_trail.append({
            "agent": "researcher",
            "step": "data_retrieval",
            "reasoning": researcher_result.get("reasoning", "RAG retrieval completed"),
            "output": f"{len(researcher_result.get('findings', []))} findings retrieved",
            "confidence": researcher_result.get("confidence_score", 0),
            "data_sources": researcher_result.get("data_sources_used", []),
        })
    else:
        reasoning_trail.append({
            "agent": "researcher",
            "step": "data_retrieval",
            "reasoning": "Researcher agent unavailable — proceeding with context-only analysis",
            "output": "skipped",
            "confidence": 0,
            "data_sources": [],
        })

    # ── Step 3: Executor (Recommendations) ────────────────────────────
    executor_result = await _call_agent(
        "executor", EXECUTOR_URL, "/generate-recommendations",
        {
            "request": request_dict,
            "context": planner_result,
            "research_data": research_data,
        },
        task_id,
    )
    reasoning_trail.append({
        "agent": "executor",
        "step": "recommendation_generation",
        "reasoning": executor_result.get("reasoning", ""),
        "output": f"{len(executor_result.get('recommendations', []))} recommendations generated",
        "confidence": executor_result.get("confidence_score", 0),
        "data_sources": ["planner_context", "research_data"],
    })

    # Extract risks and recommendations from executor response
    risks_raw = executor_result.get("risks", [])
    recommendations_raw = executor_result.get("recommendations", [])

    # Generate alerts for high/critical risks
    for risk in risks_raw:
        sev = risk.get("severity", "medium")
        if sev in ("high", "critical"):
            _alerts.append({
                "id": str(uuid.uuid4()),
                "organization_id": request_dict.get("context", {}).get("organization_id"),
                "risk_id": risk.get("id"),
                "alert_type": "risk_detected",
                "severity": sev,
                "title": f"{sev.upper()} Risk: {risk.get('title', 'Unknown')}",
                "description": risk.get("description", ""),
                "status": "active",
                "metadata": {"task_id": task_id, "risk_category": risk.get("risk_category")},
                "created_at": datetime.utcnow().isoformat(),
            })

    # ── Step 4: Reviewer (Quality Validation) ─────────────────────────
    reviewer_result = await _call_agent(
        "reviewer", REVIEWER_URL, "/review",
        {
            "risks": risks_raw if isinstance(risks_raw, list) else [],
            "recommendations": recommendations_raw,
            "context": planner_result,
            "research_data": research_data,
        },
        task_id,
    )
    reasoning_trail.append({
        "agent": "reviewer",
        "step": "quality_review",
        "reasoning": reviewer_result.get("reasoning", ""),
        "output": reviewer_result.get("review_summary", ""),
        "confidence": reviewer_result.get("confidence_score", 0),
        "data_sources": ["executor_output", "compliance_rules"],
    })

    # ── Aggregate final response ──────────────────────────────────────
    confidence_scores = [
        step.get("confidence", 0) for step in reasoning_trail if step.get("confidence")
    ]
    overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

    return RiskAssessmentResponse(
        task_id=task_id,
        status=AssessmentStatus.COMPLETED,
        risks=risks_raw,
        recommendations=recommendations_raw,
        confidence_score=round(overall_confidence, 3),
        reasoning_trail=reasoning_trail,
        metadata={
            "planner": planner_result.get("metadata", {}),
            "researcher": research_data.get("metadata", {}) if research_data else {},
            "executor": executor_result.get("metadata", {}),
            "reviewer": {
                "quality_score": reviewer_result.get("overall_quality_score", 0),
                "approval_status": reviewer_result.get("approval_status", "conditional"),
                "issues": len(reviewer_result.get("quality_issues", [])),
            },
            "pipeline_agents": ["planner", "researcher", "executor", "reviewer"],
        },
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check — also probes downstream agents."""
    services = {}
    for name, url in [
        ("planner", PLANNER_URL),
        ("researcher", RESEARCHER_URL),
        ("executor", EXECUTOR_URL),
        ("reviewer", REVIEWER_URL),
    ]:
        try:
            resp = await _http_client.get(f"{url}/health", timeout=3.0)
            services[name] = "healthy" if resp.status_code == 200 else "degraded"
        except Exception:
            services[name] = "unreachable"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"
    return {"status": overall, "agent": "coordinator", "services": services}


@app.get("/ready")
async def ready():
    """Readiness probe — returns 200 when the coordinator can accept work."""
    return {"status": "ready", "agent": "coordinator"}


@app.post("/assess-risk")
async def assess_risk(request: RiskAssessmentRequest):
    """
    Primary endpoint: initiate a full risk assessment workflow.
    Creates a task, runs the pipeline, and returns the result.
    """
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    _tasks[task_id] = {
        "status": "processing",
        "started_at": datetime.utcnow().isoformat(),
        "request": request.model_dump(mode="json"),
    }

    try:
        result = await _run_pipeline(task_id, request)
        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
        _tasks[task_id]["result"] = result.model_dump(mode="json")
        return result
    except HTTPException:
        _tasks[task_id]["status"] = "failed"
        raise
    except Exception as exc:
        logger.error("Pipeline failed", task_id=task_id, error=str(exc))
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = str(exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Assessment pipeline failed: {exc}",
        )


@app.post("/process")
async def process(payload: Dict[str, Any]):
    """
    Alternate entry point used by integration tests.
    Accepts a raw dict, wraps it in RiskAssessmentRequest, runs the pipeline.
    """
    try:
        request = RiskAssessmentRequest(**payload)
    except Exception:
        request = RiskAssessmentRequest(
            entities=payload.get("entities", []),
            assessment_type=payload.get("assessment_type", "comprehensive"),
            time_horizon_days=payload.get("time_horizon_days", 30),
            context=payload.get("context"),
        )
    return await assess_risk(request)


@app.get("/tasks/{task_id}/status")
async def task_status(task_id: str):
    """Poll task status."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task_id,
        "status": task["status"],
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
        "error": task.get("error"),
    }


@app.get("/tasks/{task_id}/result")
async def task_result(task_id: str):
    """Retrieve the full result of a completed task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Task is {task['status']}, not completed")
    return task["result"]


@app.get("/risks")
async def list_risks(limit: int = 50, offset: int = 0, severity: str = None):
    """
    List risks from completed assessments.
    In production this would query the database; for now it aggregates from in-memory tasks.
    """
    all_risks = []
    for task in _tasks.values():
        if task.get("status") == "completed" and task.get("result"):
            all_risks.extend(task["result"].get("risks", []))

    if severity:
        all_risks = [r for r in all_risks if r.get("severity") == severity]

    return {
        "risks": all_risks[offset : offset + limit],
        "total": len(all_risks),
        "limit": limit,
        "offset": offset,
    }


@app.get("/risks/{risk_id}")
async def get_risk(risk_id: str):
    """Get a single risk by ID."""
    for task in _tasks.values():
        if task.get("status") == "completed" and task.get("result"):
            for risk in task["result"].get("risks", []):
                if risk.get("id") == risk_id:
                    return risk
    raise HTTPException(status_code=404, detail="Risk not found")


@app.get("/recommendations/{risk_id}")
async def get_recommendations_for_risk(risk_id: str):
    """Get recommendations associated with a specific risk."""
    for task in _tasks.values():
        if task.get("status") == "completed" and task.get("result"):
            matching = [
                r for r in task["result"].get("recommendations", [])
                if r.get("risk_id") == risk_id
            ]
            if matching:
                return {"risk_id": risk_id, "recommendations": matching}
    return {"risk_id": risk_id, "recommendations": []}


# ---------------------------------------------------------------------------
# Supplier Management (in-memory for dev, DB in production)
# ---------------------------------------------------------------------------

_suppliers = {
    "c0000000-0000-0000-0000-000000000001": {"id": "c0000000-0000-0000-0000-000000000001", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-ALPHA", "name": "Supplier Alpha", "supplier_type": "api_manufacturer", "country_code": "US", "region": "North America", "risk_score": 35.0, "risk_tier": "low", "contact_name": "John Smith", "contact_email": "john@supplier-alpha.com", "is_active": True},
    "c0000000-0000-0000-0000-000000000002": {"id": "c0000000-0000-0000-0000-000000000002", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-BETA", "name": "Supplier Beta", "supplier_type": "excipient_supplier", "country_code": "DE", "region": "Europe", "risk_score": 62.0, "risk_tier": "medium", "contact_name": "Hans Mueller", "contact_email": "hans@supplier-beta.de", "is_active": True},
    "c0000000-0000-0000-0000-000000000003": {"id": "c0000000-0000-0000-0000-000000000003", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-GAMMA", "name": "Supplier Gamma", "supplier_type": "packaging", "country_code": "CN", "region": "Asia Pacific", "risk_score": 78.0, "risk_tier": "high", "contact_name": "Wei Zhang", "contact_email": "wei@supplier-gamma.cn", "is_active": True},
    "c0000000-0000-0000-0000-000000000004": {"id": "c0000000-0000-0000-0000-000000000004", "organization_id": "a0000000-0000-0000-0000-000000000002", "supplier_code": "SUP-DELTA", "name": "Supplier Delta", "supplier_type": "sensor_components", "country_code": "JP", "region": "Asia Pacific", "risk_score": 28.0, "risk_tier": "low", "contact_name": "Yuki Tanaka", "contact_email": "yuki@supplier-delta.jp", "is_active": True},
    "c0000000-0000-0000-0000-000000000005": {"id": "c0000000-0000-0000-0000-000000000005", "organization_id": "a0000000-0000-0000-0000-000000000002", "supplier_code": "SUP-EPSILON", "name": "Supplier Epsilon", "supplier_type": "biocompatible_materials", "country_code": "US", "region": "North America", "risk_score": 55.0, "risk_tier": "medium", "contact_name": "Sarah Johnson", "contact_email": "sarah@supplier-epsilon.com", "is_active": True},
}

_alerts: List[Dict[str, Any]] = []


@app.get("/suppliers")
async def list_suppliers(org_id: str = None, risk_tier: str = None, limit: int = 50):
    """List suppliers with optional filters."""
    suppliers = list(_suppliers.values())
    if org_id:
        suppliers = [s for s in suppliers if s.get("organization_id") == org_id]
    if risk_tier:
        suppliers = [s for s in suppliers if s.get("risk_tier") == risk_tier]
    return {"suppliers": suppliers[:limit], "total": len(suppliers)}


@app.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str):
    """Get a single supplier profile."""
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@app.post("/suppliers")
async def create_supplier(supplier: Dict[str, Any]):
    """Create a new supplier."""
    supplier_id = str(uuid.uuid4())
    supplier["id"] = supplier_id
    _suppliers[supplier_id] = supplier
    return supplier


@app.put("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, updates: Dict[str, Any]):
    """Update supplier details."""
    if supplier_id not in _suppliers:
        raise HTTPException(status_code=404, detail="Supplier not found")
    _suppliers[supplier_id].update(updates)
    return _suppliers[supplier_id]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.get("/alerts")
async def list_alerts(status_filter: str = None, severity: str = None, limit: int = 50):
    """List alerts with optional filters."""
    alerts = list(_alerts)
    if status_filter:
        alerts = [a for a in alerts if a.get("status") == status_filter]
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]
    return {"alerts": alerts[:limit], "total": len(alerts)}


@app.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    for alert in _alerts:
        if alert.get("id") == alert_id:
            alert["status"] = "acknowledged"
            alert["acknowledged_at"] = datetime.utcnow().isoformat()
            return alert
    raise HTTPException(status_code=404, detail="Alert not found")


# ---------------------------------------------------------------------------
# Risk History
# ---------------------------------------------------------------------------

@app.get("/risks/history")
async def risk_history(limit: int = 100):
    """Get historical risk data from all completed assessments."""
    history = []
    for task_id, task in _tasks.items():
        if task.get("status") == "completed" and task.get("result"):
            for risk in task["result"].get("risks", []):
                history.append({
                    **risk,
                    "assessment_task_id": task_id,
                    "assessment_completed_at": task.get("completed_at"),
                })
    history.sort(key=lambda r: r.get("detected_at", ""), reverse=True)
    return {"history": history[:limit], "total": len(history)}


# ---------------------------------------------------------------------------
# Predictive Alerts (7-day forecasting based on risk trends)
# ---------------------------------------------------------------------------

@app.get("/predictions")
async def get_predictions():
    """Generate 7-day disruption predictions based on current risk landscape."""
    all_risks = []
    for task in _tasks.values():
        if task.get("status") == "completed" and task.get("result"):
            all_risks.extend(task["result"].get("risks", []))

    if not all_risks:
        return {"predictions": [], "horizon_days": 7, "model": "rule-based"}

    # Group risks by category and compute trend scores
    category_scores: Dict[str, list] = {}
    for risk in all_risks:
        cat = risk.get("risk_category", "general")
        prob = risk.get("probability", 0.5)
        impact = risk.get("impact_score", 5.0)
        category_scores.setdefault(cat, []).append(prob * impact)

    predictions = []
    for category, scores in category_scores.items():
        avg_score = sum(scores) / len(scores)
        risk_count = len(scores)
        # Simple prediction: higher avg score + more occurrences = higher disruption probability
        disruption_prob = min(avg_score / 10.0 * (1 + risk_count * 0.1), 0.95)
        severity = (
            "critical" if disruption_prob > 0.8
            else "high" if disruption_prob > 0.6
            else "medium" if disruption_prob > 0.3
            else "low"
        )
        predictions.append({
            "id": str(uuid.uuid4()),
            "category": category,
            "predicted_disruption_probability": round(disruption_prob, 3),
            "severity": severity,
            "risk_count": risk_count,
            "average_impact": round(avg_score, 2),
            "horizon_days": 7,
            "recommendation": f"Monitor {category} risks closely — {risk_count} active risk(s) detected with avg impact {avg_score:.1f}",
        })

    predictions.sort(key=lambda p: p["predicted_disruption_probability"], reverse=True)
    return {"predictions": predictions, "horizon_days": 7, "model": "rule-based", "total": len(predictions)}


# ---------------------------------------------------------------------------
# Supply Chain Map (node graph for visualization)
# ---------------------------------------------------------------------------

@app.get("/supply-chain/map")
async def supply_chain_map(org_id: str = None):
    """Get supply chain topology as nodes and edges for visualization."""
    # Build nodes from suppliers + org
    nodes = []
    edges = []

    # Organization nodes
    orgs_used = set()
    for s in _suppliers.values():
        if org_id and s.get("organization_id") != org_id:
            continue
        org_oid = s.get("organization_id", "unknown")
        if org_oid not in orgs_used:
            nodes.append({
                "id": org_oid,
                "type": "organization",
                "label": f"Org {org_oid[:8]}",
                "risk_score": 0,
            })
            orgs_used.add(org_oid)

        nodes.append({
            "id": s["id"],
            "type": "supplier",
            "label": s["name"],
            "supplier_type": s.get("supplier_type", "general"),
            "country_code": s.get("country_code", ""),
            "region": s.get("region", ""),
            "risk_score": s.get("risk_score", 50),
            "risk_tier": s.get("risk_tier", "medium"),
        })
        edges.append({
            "source": s["id"],
            "target": org_oid,
            "relationship": "supplies",
        })

    # Add risk nodes from recent assessments
    for task in _tasks.values():
        if task.get("status") == "completed" and task.get("result"):
            for risk in task["result"].get("risks", []):
                nodes.append({
                    "id": risk.get("id", str(uuid.uuid4())),
                    "type": "risk",
                    "label": risk.get("title", "Unknown Risk"),
                    "severity": risk.get("severity", "medium"),
                    "risk_category": risk.get("risk_category", ""),
                })
                # Link risks to affected entities
                for entity_id in risk.get("affected_entities", []):
                    edges.append({
                        "source": risk.get("id"),
                        "target": entity_id,
                        "relationship": "affects",
                    })

    return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes), "total_edges": len(edges)}


# ---------------------------------------------------------------------------
# Scenario Simulation
# ---------------------------------------------------------------------------

@app.post("/scenarios/simulate")
async def simulate_scenario(scenario: Dict[str, Any]):
    """
    Simulate a supply chain disruption scenario.
    Takes a hypothetical event and predicts impact using the agent pipeline.
    """
    scenario_type = scenario.get("type", "supplier_disruption")
    affected_suppliers = scenario.get("affected_suppliers", [])
    severity_override = scenario.get("severity", "high")
    duration_days = scenario.get("duration_days", 30)

    # Find affected suppliers
    impacted = []
    for sid in affected_suppliers:
        supplier = _suppliers.get(sid)
        if supplier:
            impacted.append(supplier)

    if not impacted and not scenario.get("description"):
        raise HTTPException(status_code=400, detail="Provide affected_suppliers or a description")

    # Calculate simulated impact
    total_risk_score = sum(s.get("risk_score", 50) for s in impacted)
    avg_risk = total_risk_score / len(impacted) if impacted else 50
    impact_multiplier = {"low": 0.5, "medium": 1.0, "high": 1.5, "critical": 2.0}.get(severity_override, 1.0)
    duration_factor = min(duration_days / 30, 3.0)

    estimated_financial_impact = avg_risk * impact_multiplier * duration_factor * 10000
    recovery_time_days = int(duration_days * (1 + avg_risk / 100))

    recommendations = []
    for supplier in impacted:
        recommendations.append({
            "action": f"Activate backup supplier for {supplier['name']}",
            "priority": "high" if supplier.get("risk_score", 50) > 60 else "medium",
            "estimated_cost": supplier.get("risk_score", 50) * 1000,
            "timeline_days": min(int(duration_days * 0.3), 14),
        })

    return {
        "scenario_id": str(uuid.uuid4()),
        "scenario_type": scenario_type,
        "severity": severity_override,
        "affected_suppliers": [s["name"] for s in impacted],
        "impact_analysis": {
            "estimated_financial_impact": round(estimated_financial_impact, 2),
            "supply_disruption_probability": round(min(avg_risk / 100 * impact_multiplier, 0.95), 3),
            "estimated_recovery_days": recovery_time_days,
            "affected_supply_chains": len(impacted),
        },
        "recommendations": recommendations,
        "simulation_confidence": round(0.6 + len(impacted) * 0.05, 2),
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("COORDINATOR_SERVICE_PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
