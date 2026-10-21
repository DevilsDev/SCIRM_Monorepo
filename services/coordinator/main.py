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
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncio

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.models import (
    AssessmentStatus,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
)
from libs.common.monitoring import setup_monitoring, track_agent_task
from libs.common import secret_box
from libs.common.security import setup_cors
from libs.common.store import create_store
from libs.common.tenancy import internal_headers, tenant_org
from libs.integrations import sap_import, sap_odata, sap_spend
from libs.intel import geo

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PLANNER_URL = os.getenv("PLANNER_SERVICE_URL", "http://localhost:8002")
RESEARCHER_URL = os.getenv("RESEARCHER_SERVICE_URL", "http://localhost:8003")
EXECUTOR_URL = os.getenv("EXECUTOR_SERVICE_URL", "http://localhost:8004")
REVIEWER_URL = os.getenv("REVIEWER_SERVICE_URL", "http://localhost:8005")
DISCOVERY_URL = os.getenv("DISCOVERY_SERVICE_URL", "http://localhost:8007")
INGESTION_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8008")
AGENT_TIMEOUT = float(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))
AUTO_REFRESH_INTERVAL = int(os.getenv("AUTO_REFRESH_INTERVAL_MINUTES", "15"))
# Off by default: each refresh stores a new copy of every risk, so persisted data
# would grow without bound. Re-enable once refreshes supersede earlier results.
AUTO_REFRESH_ENABLED = os.getenv("AUTO_REFRESH_ENABLED", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logger = structlog.get_logger()

# Tenant data: MemoryStore in development/tests, PostgresStore otherwise (see libs/common/store.py).
store = create_store()
# ERP connection passwords are decrypted here, to call SAP: fail at start-up without the key.
secret_box.require_key()

# Shared HTTP client
_http_client: Optional[httpx.AsyncClient] = None


async def _get_org_supplier(org_id: str, supplier_id: str) -> Dict[str, Any]:
    supplier = await store.get_supplier(org_id, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


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
    await store.close()
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

            # Collect unique entities from previous assessments, per organization
            entities_by_org = await store.refresh_candidates()

            if not entities_by_org:
                logger.info("Auto-refresh: no entities to re-assess, skipping")
                continue

            # Re-assess each organization's entities under that organization
            for org_id, org_entities in entities_by_org.items():
                request = RiskAssessmentRequest(
                    entities=[
                        {"id": e.get("id", ""), "name": e.get("name", ""), "type": e.get("type", ""), "location": e.get("location")}
                        for e in org_entities[:20]  # Cap at 20 entities per refresh
                    ],
                    assessment_type="refresh",
                    context={"organization_id": org_id},
                )

                task_id = f"refresh-{uuid.uuid4().hex[:8]}"
                await store.create_task(org_id, task_id, request.model_dump(mode="json"))
                result = await _run_pipeline(task_id, request)
                await store.complete_task(org_id, task_id, result.model_dump(mode="json"))

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


class AgentUnavailable(Exception):
    """An optional agent could not be reached; the caller records it as degraded."""


async def _call_agent(
    service_name: str,
    url: str,
    endpoint: str,
    payload: Dict[str, Any],
    task_id: str,
    required: bool = True,
) -> Dict[str, Any]:
    """Call a downstream agent and return its JSON response.

    A required agent that cannot be reached fails the request (503). An optional
    agent raises AgentUnavailable so the caller can mark the result degraded —
    never silently treat "unreachable" as "nothing found".
    """
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

    except httpx.TimeoutException as exc:
        logger.error("Agent timeout", agent=service_name, url=full_url, task_id=task_id)
        if not required:
            raise AgentUnavailable(service_name) from exc
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
    except httpx.TransportError as exc:
        logger.warning("Agent unreachable", agent=service_name, url=full_url, task_id=task_id, error=type(exc).__name__)
        if not required:
            raise AgentUnavailable(service_name) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{service_name} agent is unavailable",
        )


# ---------------------------------------------------------------------------
# Orchestration pipeline
# ---------------------------------------------------------------------------

@track_agent_task("coordinator", "risk_assessment")
async def _run_pipeline(task_id: str, request: RiskAssessmentRequest) -> RiskAssessmentResponse:
    """Execute the full agent pipeline: Planner → Researcher → Executor → Reviewer."""
    reasoning_trail = []
    request_dict = request.model_dump(mode="json")
    # Degraded-result contract: every way this result is weaker than a full run.
    data_quality: Dict[str, Any] = {"degraded": False, "unavailable_agents": [], "warnings": []}

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
    try:
        researcher_result = await _call_agent(
            "researcher", RESEARCHER_URL, "/research",
            {
                "query": f"supply chain risks for {request.assessment_type or 'comprehensive'} assessment",
                "data_sources": ["weather", "logistics", "news", "regulatory"],
                "entities": request_dict.get("entities", []),
                "context": planner_result,
            },
            task_id,
            required=False,
        )
    except AgentUnavailable:
        researcher_result = None
        data_quality["degraded"] = True
        data_quality["unavailable_agents"].append("researcher")
        data_quality["warnings"].append(
            "External intelligence was not retrieved (researcher agent unavailable); "
            "risks reflect organizational context only."
        )
    if researcher_result and researcher_result.get("metadata", {}).get("demo_data"):
        data_quality["degraded"] = True
        data_quality["warnings"].append(
            "Research used the built-in sample corpus, not live intelligence feeds."
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
    pipeline_org = request_dict.get("context", {}).get("organization_id")
    new_alerts: List[Dict[str, Any]] = []
    for risk in risks_raw:
        sev = risk.get("severity", "medium")
        if sev in ("high", "critical"):
            new_alerts.append({
                "id": str(uuid.uuid4()),
                "organization_id": pipeline_org,
                "risk_id": risk.get("id"),
                "alert_type": "risk_detected",
                "severity": sev,
                "title": f"{sev.upper()} Risk: {risk.get('title', 'Unknown')}",
                "description": risk.get("description", ""),
                "status": "active",
                "metadata": {"task_id": task_id, "risk_category": risk.get("risk_category")},
                "created_at": datetime.utcnow().isoformat(),
            })

    if pipeline_org:
        await store.add_alerts(pipeline_org, new_alerts)

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
            "data_quality": data_quality,
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
async def assess_risk(request: RiskAssessmentRequest, org_id: str = Depends(tenant_org)):
    """
    Primary endpoint: initiate a full risk assessment workflow.
    Creates a task, runs the pipeline, and returns the result.
    """
    # The tenant comes from the authenticated caller, never from the request body.
    request.context = {**(request.context or {}), "organization_id": org_id}
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    await store.create_task(org_id, task_id, request.model_dump(mode="json"))

    try:
        result = await _run_pipeline(task_id, request)
        await store.complete_task(org_id, task_id, result.model_dump(mode="json"))
        return result
    except HTTPException as exc:
        await store.fail_task(org_id, task_id, str(exc.detail))
        raise
    except Exception as exc:
        logger.error("Pipeline failed", task_id=task_id, error=str(exc))
        await store.fail_task(org_id, task_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Assessment pipeline failed: {exc}",
        )


@app.post("/process")
async def process(payload: Dict[str, Any], org_id: str = Depends(tenant_org)):
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
    return await assess_risk(request, org_id)


@app.get("/tasks/{task_id}/status")
async def task_status(task_id: str, org_id: str = Depends(tenant_org)):
    """Poll task status."""
    task = await store.get_task(org_id, task_id)
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
async def task_result(task_id: str, org_id: str = Depends(tenant_org)):
    """Retrieve the full result of a completed task."""
    task = await store.get_task(org_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Task is {task['status']}, not completed")
    return task["result"]


# ---------------------------------------------------------------------------
# Risk History
# ---------------------------------------------------------------------------

@app.get("/risks/history")
async def risk_history(limit: int = 100, org_id: str = Depends(tenant_org)):
    """Get historical risk data from all completed assessments."""
    history, total = await store.risk_history(org_id, limit)
    return {"history": history, "total": total}

@app.get("/risks")
async def list_risks(limit: int = 50, offset: int = 0, severity: str = None, org_id: str = Depends(tenant_org)):
    """
    List risks from completed assessments.
    In production this would query the database; for now it aggregates from in-memory tasks.
    """
    risks, total = await store.list_risks(org_id, severity=severity, limit=limit, offset=offset)
    return {
        "risks": risks,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@app.get("/risks/{risk_id}")
async def get_risk(risk_id: str, org_id: str = Depends(tenant_org)):
    """Get a single risk by ID."""
    risk = await store.get_risk(org_id, risk_id)
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    return risk


@app.post("/risks")
async def create_risk(body: Dict[str, Any], org_id: str = Depends(tenant_org)):
    """Create a manual risk entry."""
    risk_id = str(uuid.uuid4())
    risk = {
        "id": risk_id,
        "organization_id": org_id,
        "title": body.get("title", ""),
        "description": body.get("description", ""),
        "severity": body.get("severity", "medium"),
        "probability": body.get("probability", 0.5),
        "impact_score": body.get("impact_score", 5.0),
        "affected_entities": body.get("affected_entities", []),
        "risk_category": body.get("risk_category", ""),
        "detected_at": datetime.utcnow().isoformat(),
        "predicted_occurrence": body.get("predicted_occurrence"),
        "data_sources": ["manual_entry"],
        "status": body.get("status", "open"),
        "owner": body.get("owner"),
    }
    return await store.create_risk(org_id, risk)


@app.put("/risks/{risk_id}")
async def update_risk(risk_id: str, body: Dict[str, Any], org_id: str = Depends(tenant_org)):
    """Update a risk entry."""
    # Identity and tenancy fields are not client-editable (enforced by the store).
    risk = await store.update_risk(org_id, risk_id, body)
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    return risk


@app.get("/recommendations/{risk_id}")
async def get_recommendations_for_risk(risk_id: str, org_id: str = Depends(tenant_org)):
    """Get recommendations associated with a specific risk."""
    return {"risk_id": risk_id, "recommendations": await store.recommendations_for_risk(org_id, risk_id)}

# ---------------------------------------------------------------------------
# Supplier Management (in-memory for dev, DB in production)
# ---------------------------------------------------------------------------

def _presented(supplier: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A supplier as the API shows it. A risk score or tier is only shown once an
    assessment recorded one (risk_assessed_at); otherwise the stored values are
    placeholders (defaults or demo seed data) and must not read as a rating."""
    if supplier is None:
        return None
    out = dict(supplier)
    if not out.get("risk_assessed_at"):
        out["risk_score"] = None
        out["risk_tier"] = None
    return out


@app.get("/suppliers")
async def list_suppliers(risk_tier: str = None, limit: int = 50, org_id: str = Depends(tenant_org)):
    """List suppliers with optional filters."""
    suppliers, total = await store.list_suppliers(org_id)
    shown = [_presented(s) for s in suppliers]
    if risk_tier:
        shown = [s for s in shown if s["risk_tier"] == risk_tier]
        total = len(shown)
    return {"suppliers": shown[:limit], "total": total}


class SupplierImport(BaseModel):
    content: str = Field(..., min_length=1, max_length=20_000_000)
    column_map: Dict[str, str] = Field(default_factory=dict)
    # Possible duplicates: {SAP number: "create" | "link:<supplier id>"}.
    decisions: Dict[str, str] = Field(default_factory=dict)
    deactivate_missing: bool = False
    apply: bool = False


async def _supplier_import(org_id: str, rows: List[Dict[str, Any]], warnings: List[str], decisions: Dict[str, str],
                           deactivate_missing: bool, apply: bool) -> Dict[str, Any]:
    """Plan (and with apply, write) a supplier master import, from a file or from SAP."""
    existing, _ = await store.list_suppliers(org_id, limit=None)
    plan = sap_import.plan_import(rows, existing, decisions, deactivate_missing)
    written = 0
    if apply:
        creates = [{"supplier_type": "general", **a["fields"]} for a in plan["actions"] if a["action"] == "create"]
        updates = [(a["supplier_id"], a["fields"]) for a in plan["actions"]
                   if a["action"] in ("update", "link", "deactivate")]
        try:
            # One transaction: a failure leaves the suppliers as they were.
            written = await store.write_suppliers(org_id, creates, updates)
        except KeyError:
            raise HTTPException(status_code=409, detail="Suppliers changed during the import. Preview again.")
    return {"applied": apply, "written": written, "rows": len(rows), "warnings": warnings,
            "summary": plan["summary"], "duplicates": plan["duplicates"], "missing": plan["missing"],
            "missing_deactivated": plan["missing_deactivated"], "guard": plan["guard"],
            # Unchanged suppliers are only counted, to keep the response small.
            "actions": [a for a in plan["actions"] if a["action"] != "unchanged"][:2000]}


@app.post("/suppliers/import/sap")
async def import_sap_suppliers(body: SupplierImport, org_id: str = Depends(tenant_org)):
    """Supplier master from an SAP LFA1 extract. With apply=false (the default) nothing is
    written: the response is the preview. Applying re-plans against current data."""
    rows, warnings = sap_import.parse_extract(body.content, body.column_map)
    if not rows:
        raise HTTPException(status_code=400, detail=" ".join(warnings) or "No suppliers found in the file")
    return await _supplier_import(org_id, rows, warnings, body.decisions, body.deactivate_missing, body.apply)


class SpendImport(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000_000)
    column_map: Dict[str, str] = Field(default_factory=dict)
    decimal: Optional[str] = Field(None, pattern=r"^[.,]$")
    apply: bool = False


async def _spend_import(org_id: str, summary: Dict[str, Any], warnings: List[str], apply: bool) -> Dict[str, Any]:
    """Plan (and with apply, write) supplier spend, from a file or from SAP."""
    existing, _ = await store.list_suppliers(org_id, limit=None)
    plan = sap_spend.plan_spend(summary, existing)
    if not plan["updates"]:
        warnings.append("No suppliers have been imported from SAP yet. Import the supplier master (LFA1) first.")
    written = 0
    if apply and plan["updates"]:
        try:
            written = await store.write_suppliers(org_id, [], [(u["supplier_id"], u["fields"]) for u in plan["updates"]])
        except KeyError:
            raise HTTPException(status_code=409, detail="Suppliers changed during the import. Preview again.")
    return {"applied": apply, "written": written, "warnings": warnings,
            **{k: plan[k] for k in ("period", "main_currency", "currencies", "lines", "top", "unknown_suppliers",
                                    "unknown_count", "with_spend")},
            "suppliers": len(plan["updates"])}


@app.post("/suppliers/import/sap-spend")
async def import_sap_spend(body: SpendImport, org_id: str = Depends(tenant_org)):
    """12-month purchase-order spend per SAP supplier, from an EKKO/EKPO (or ME2N) export.
    Preview unless apply=true; applying replaces earlier spend, in one transaction."""
    lines, warnings = sap_spend.parse_po_extract(body.content, body.column_map, body.decimal)
    if not lines:
        raise HTTPException(status_code=400, detail=" ".join(warnings) or "No purchase-order lines found in the file")
    return await _spend_import(org_id, sap_spend.summarize(lines), warnings, body.apply)


# --- direct SAP connection (S/4HANA OData; libs/integrations/sap_odata.py) ----------

class SapConnectionBody(BaseModel):
    base_url: str = Field(..., min_length=8, max_length=500)
    sap_client: Optional[str] = Field(None, max_length=3)
    username: str = Field(..., min_length=1, max_length=200)
    # Omitted when changing other settings: the stored password is kept.
    password: Optional[str] = Field(None, min_length=1, max_length=500)
    actor: Optional[str] = Field(None, max_length=320)


class ConnectionSupplierImport(BaseModel):
    decisions: Dict[str, str] = Field(default_factory=dict)
    deactivate_missing: bool = False
    apply: bool = False


class ConnectionSpendImport(BaseModel):
    apply: bool = False


@app.get("/integrations/sap")
async def get_sap_connection(org_id: str = Depends(tenant_org)):
    """The tenant's SAP connection, without its password."""
    return {"connection": await store.get_erp_connection(org_id, "sap")}


@app.put("/integrations/sap")
async def save_sap_connection(body: SapConnectionBody, org_id: str = Depends(tenant_org)):
    try:
        fields = {"base_url": sap_odata.validate_base_url(body.base_url),
                  "sap_client": sap_odata.validate_client(body.sap_client), "username": body.username.strip()}
    except sap_odata.SapError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    saved = await store.save_erp_connection(org_id, "sap", fields, body.password, body.actor)
    if saved is None:
        raise HTTPException(status_code=400, detail="Enter the password of the SAP communication user.")
    return {"connection": saved}


@app.delete("/integrations/sap")
async def delete_sap_connection(org_id: str = Depends(tenant_org)):
    """Remove the connection and its stored password. Imported suppliers stay."""
    if not await store.delete_erp_connection(org_id, "sap"):
        raise HTTPException(status_code=404, detail="No SAP connection is set up")
    return {"deleted": True}


async def _sap_connection(org_id: str) -> Dict[str, Any]:
    try:
        connection = await store.get_erp_connection(org_id, "sap", with_password=True)
    except secret_box.SecretBoxError:
        logger.error("SAP connection password cannot be decrypted", org=org_id)
        raise HTTPException(status_code=409, detail="The stored SAP password can no longer be read (the encryption "
                                                    "key changed). Enter the password again.")
    if connection is None:
        raise HTTPException(status_code=404, detail="No SAP connection is set up")
    return connection


@app.post("/integrations/sap/test")
async def test_sap_connection(org_id: str = Depends(tenant_org)):
    """Check that both SAP services can be read with the stored settings."""
    result = await sap_odata.check_connection(await _sap_connection(org_id))
    await store.record_erp_result(org_id, "sap", "last_test", result)
    return result


async def _record_import(org_id: str, kind: str, result: Dict[str, Any], error: Optional[str] = None) -> None:
    summary = {"kind": kind, "ok": error is None, "error": error}
    if error is None:
        summary.update(applied=result.get("applied"), written=result.get("written"))
    await store.record_erp_result(org_id, "sap", "last_import", summary)


@app.post("/suppliers/import/sap/connection")
async def import_sap_suppliers_from_connection(body: ConnectionSupplierImport, org_id: str = Depends(tenant_org)):
    """The supplier master read from the tenant's SAP system. Like the file import:
    preview unless apply=true. Applying reads SAP again and re-plans."""
    connection = await _sap_connection(org_id)
    try:
        rows, warnings = await sap_odata.fetch_suppliers(connection)
    except sap_odata.SapError as exc:
        await _record_import(org_id, "suppliers", {}, str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    if not rows:
        raise HTTPException(status_code=400, detail=" ".join(warnings) or "SAP returned no suppliers")
    result = await _supplier_import(org_id, rows, warnings, body.decisions, body.deactivate_missing, body.apply)
    await _record_import(org_id, "suppliers", result)
    return {**result, "source": "connection"}


@app.post("/suppliers/import/sap-spend/connection")
async def import_sap_spend_from_connection(body: ConnectionSpendImport, org_id: str = Depends(tenant_org)):
    """Purchase-order spend for the last 365 days, read from the tenant's SAP system."""
    connection = await _sap_connection(org_id)
    try:
        lines, warnings, end = await sap_odata.fetch_orders(connection)
    except sap_odata.SapError as exc:
        await _record_import(org_id, "spend", {}, str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    if not lines:
        # Like an empty file: applying would set every SAP supplier's spend to zero. A user
        # whose authorizations hide orders gets an empty, complete-looking answer from SAP.
        since = (end - timedelta(days=sap_spend.PERIOD_DAYS - 1)).isoformat()
        detail = (f"SAP returned no purchase orders dated since {since}. Check that the communication user "
                  "can see all purchase orders. Nothing was imported.")
        await _record_import(org_id, "spend", {}, detail)
        raise HTTPException(status_code=400, detail=" ".join([detail, *warnings]))
    result = await _spend_import(org_id, sap_spend.summarize(lines, end=end), warnings, body.apply)
    await _record_import(org_id, "spend", result)
    return {**result, "source": "connection"}


@app.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str, org_id: str = Depends(tenant_org)):
    """Get a single supplier profile."""
    return _presented(await _get_org_supplier(org_id, supplier_id))


@app.post("/suppliers")
async def create_supplier(supplier: Dict[str, Any], org_id: str = Depends(tenant_org)):
    """Create a new supplier."""
    # The store assigns the id and the caller's organization. Scores come from assessments,
    # not from the request.
    supplier = {k: v for k, v in supplier.items() if k not in ("risk_score", "risk_tier", "risk_assessed_at")}
    return _presented(await store.create_supplier(org_id, supplier))


@app.put("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, updates: Dict[str, Any], org_id: str = Depends(tenant_org)):
    """Update supplier details."""
    # Identity and tenancy fields are not client-editable (enforced by the store).
    # Scores come from assessments; sites go through /sites (validated and located).
    updates = {k: v for k, v in updates.items() if k not in ("risk_score", "risk_tier", "risk_assessed_at", "sites")}
    supplier = await store.update_supplier(org_id, supplier_id, updates)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return _presented(supplier)


class SiteInput(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., pattern=r"^[A-Za-z]{2}$")
    city: Optional[str] = Field(None, max_length=100)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)


MAX_SITES = 50


@app.post("/suppliers/{supplier_id}/sites")
async def add_site(supplier_id: str, site: SiteInput, org_id: str = Depends(tenant_org)):
    """Add a place the supplier operates. Exact coordinates are used as given; otherwise
    the city is looked up in the offline gazetteer (city-level precision)."""
    supplier = await _get_org_supplier(org_id, supplier_id)
    sites = [x for x in supplier.get("sites") or [] if isinstance(x, dict)]
    if len(sites) >= MAX_SITES:
        raise HTTPException(status_code=400, detail=f"A supplier can have at most {MAX_SITES} sites")
    country = site.country.upper()
    if (site.lat is None) != (site.lon is None):
        raise HTTPException(status_code=400, detail="Give both latitude and longitude, or neither")
    if site.lat is not None:
        entry = {"label": site.label.strip(), "city": (site.city or "").strip() or None, "country": country,
                 "lat": site.lat, "lon": site.lon, "source": "manual", "precision": "exact"}
    else:
        entry = geo.site_from_address(site.label.strip(), (site.city or "").strip(), country, "manual")
        if entry is None:
            raise HTTPException(status_code=400, detail=(
                f"'{site.city or ''}' was not found in {country}. Check the spelling, use the nearest larger "
                "town, or enter the coordinates."))
    entry["id"] = str(uuid.uuid4())
    updated = await store.update_supplier(org_id, supplier_id, {"sites": sites + [entry]})
    return _presented(updated)


@app.delete("/suppliers/{supplier_id}/sites/{site_id}")
async def remove_site(supplier_id: str, site_id: str, org_id: str = Depends(tenant_org)):
    """Remove a site. A site from the SAP address comes back on the next SAP import."""
    supplier = await _get_org_supplier(org_id, supplier_id)
    sites = [x for x in supplier.get("sites") or [] if isinstance(x, dict)]
    kept = [x for x in sites if x.get("id") != site_id]
    if len(kept) == len(sites):
        raise HTTPException(status_code=404, detail="Site not found")
    return _presented(await store.update_supplier(org_id, supplier_id, {"sites": kept}))


# ---------------------------------------------------------------------------
# Public signals matched to this tenant's suppliers
# ---------------------------------------------------------------------------

async def _match_signals(org_id: str, suppliers: List[Dict[str, Any]], **options: Any) -> Dict[str, Any]:
    """Ask the ingestion service which public signals concern these suppliers.
    Only this tenant's suppliers are sent; the ingestion service stores none of them."""
    payload = {"suppliers": [{k: s.get(k) for k in ("id", "name", "country_code", "aliases", "sites")} for s in suppliers],
               **{k: v for k, v in options.items() if v is not None}}
    try:
        url, headers = f"{INGESTION_URL}/match", internal_headers(org_id)
        if _http_client is not None:
            response = await _http_client.post(url, json=payload, headers=headers)
        else:  # outside the app lifespan (e.g. tests)
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        return {"matches": body["matches"], "totals": body.get("totals", {})}
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Signal matching unavailable", error=type(exc).__name__)
        raise HTTPException(status_code=503, detail="Public signal matching is unavailable")


def _split(matches: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {"incidents": [m for m in matches if m["kind"] == "incident"],
            "exposures": [m for m in matches if m["kind"] == "exposure"]}


@app.get("/suppliers/{supplier_id}/signals")
async def supplier_signals(supplier_id: str, since_days: Optional[int] = None, min_confidence: Optional[float] = None,
                           org_id: str = Depends(tenant_org)):
    """Public records naming this supplier (incidents) or affecting its country (exposures)."""
    supplier = await _get_org_supplier(org_id, supplier_id)
    result = await _match_signals(org_id, [supplier], since_days=since_days, min_confidence=min_confidence)
    sid = str(supplier["id"])
    totals = result["totals"].get(sid, {})
    parts = _split(result["matches"].get(sid, []))
    return {"supplier_id": supplier["id"], "supplier_name": supplier.get("name"), **parts,
            # The lists are capped; these are the full counts.
            # Incidents are events; one FDA recall event can cover many recall records.
            "incident_total": totals.get("incidents", len(parts["incidents"])),
            "incident_records": totals.get("incident_records", len(parts["incidents"])),
            "exposure_total": totals.get("exposures", len(parts["exposures"])),
            # With located sites, exposure is judged per site; alerts elsewhere in its countries are counted here.
            "site_level": totals.get("site_level", False),
            "exposures_elsewhere": totals.get("exposures_elsewhere", 0)}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@app.post("/suppliers/{supplier_id}/ask")
async def ask_about_supplier(supplier_id: str, request: AskRequest, org_id: str = Depends(tenant_org)):
    """Answer a question about one of this tenant's suppliers from public records.
    Only this supplier is sent to the Evidence Engine; the question is not stored."""
    supplier = await _get_org_supplier(org_id, supplier_id)
    payload = {"question": request.question,
               "supplier": {k: supplier.get(k) for k in ("id", "name", "country_code", "aliases", "sites")}}
    url, headers = f"{INGESTION_URL}/evidence/ask", internal_headers(org_id)
    try:
        if _http_client is not None:
            response = await _http_client.post(url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Evidence Engine unavailable", error=type(exc).__name__)
        raise HTTPException(status_code=503, detail="Answering is unavailable")


_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@app.get("/signals/suppliers")
async def signals_overview(since_days: Optional[int] = 365, org_id: str = Depends(tenant_org)):
    """Per supplier: how many public incidents and exposures, and the worst severity."""
    suppliers, _ = await store.list_suppliers(org_id)
    result = await _match_signals(org_id, suppliers, since_days=since_days, limit_per_supplier=500)
    rows = []
    for s in suppliers:
        sid = str(s["id"])
        parts = _split(result["matches"].get(sid, []))
        incidents = parts["incidents"]
        totals = result["totals"].get(sid, {})
        rows.append({
            "supplier_id": s["id"], "supplier_name": s.get("name"), "country_code": s.get("country_code"),
            "incidents": totals.get("incidents", len(incidents)), "exposures": totals.get("exposures", len(parts["exposures"])),
            # Back-tested recall-history flag (evals/backtest): "watch", not a prediction.
            "watch": bool(totals.get("watch")), "recall_score": totals.get("recall_score"),
            "worst_incident_severity": max((m["signal"]["severity"] for m in incidents),
                                           key=lambda v: _SEVERITY_RANK.get(v, 0), default=None),
            "latest_incident_published_at": max((m["signal"]["published_at"] or "" for m in incidents), default=None),
        })
    rows.sort(key=lambda r: (_SEVERITY_RANK.get(r["worst_incident_severity"], -1), r["incidents"]), reverse=True)
    return {"suppliers": rows, "since_days": since_days}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.get("/alerts")
async def list_alerts(status_filter: str = None, severity: str = None, limit: int = 50, org_id: str = Depends(tenant_org)):
    """List alerts with optional filters."""
    alerts, total = await store.list_alerts(org_id, status=status_filter, severity=severity, limit=limit)
    return {"alerts": alerts, "total": total}


@app.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, org_id: str = Depends(tenant_org)):
    """Acknowledge an alert."""
    alert = await store.acknowledge_alert(org_id, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


# ---------------------------------------------------------------------------
# Predictive Alerts (7-day forecasting based on risk trends)
# ---------------------------------------------------------------------------

@app.get("/predictions")
async def get_predictions(org_id: str = Depends(tenant_org)):
    """Generate 7-day disruption predictions based on current risk landscape."""
    all_risks = await store.assessment_risks(org_id)

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
async def supply_chain_map(org_id: str = Depends(tenant_org)):
    """Get supply chain topology as nodes and edges for visualization."""
    # Build nodes from suppliers + org
    nodes = []
    edges = []

    # Organization nodes
    orgs_used = set()
    suppliers, _ = await store.list_suppliers(org_id)
    for s in suppliers:
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
            # Shown only if assessed (see _presented); the map draws unscored suppliers neutrally.
            "risk_score": _presented(s)["risk_score"],
            "risk_tier": _presented(s)["risk_tier"],
        })
        edges.append({
            "source": s["id"],
            "target": org_oid,
            "relationship": "supplies",
        })

    # Add risk nodes from recent assessments
    for risk in await store.assessment_risks(org_id):
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
async def simulate_scenario(scenario: Dict[str, Any], org_id: str = Depends(tenant_org)):
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
        supplier = await store.get_supplier(org_id, sid)
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
# Sub-Tier Discovery
# ---------------------------------------------------------------------------

@app.post("/discover-subtiers")
async def discover_subtiers(payload: Dict[str, Any], org_id: str = Depends(tenant_org)):
    """Discover sub-tier suppliers using the Discovery Agent."""
    try:
        return await _call_agent(
            "discovery", DISCOVERY_URL, "/discover",
            payload,
            f"discovery-{uuid.uuid4().hex[:8]}",
            required=False,
        )
    except AgentUnavailable:
        # Say so explicitly; an empty list would read as "no sub-tiers exist".
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Discovery agent is unavailable; sub-tiers were not searched")


# ---------------------------------------------------------------------------
# Risk Events + Impact Propagation
# ---------------------------------------------------------------------------

@app.post("/events")
async def create_risk_event(event: Dict[str, Any], org_id: str = Depends(tenant_org)):
    """Create a risk event and propagate impact through the supplier graph."""
    from libs.common.impact_propagation import propagate_impact

    event_id = str(uuid.uuid4())
    event["id"] = event_id
    event["organization_id"] = org_id
    event["detected_at"] = datetime.utcnow().isoformat()
    event.setdefault("status", "active")
    event = await store.create_event(org_id, event)

    # Propagate impact through supplier graph
    org_suppliers = {sup["id"]: sup for sup in (await store.list_suppliers(org_id))[0]}
    affected_ids = [sid for sid in event.get("affected_supplier_ids", []) if sid in org_suppliers]
    impacts: List[Dict[str, Any]] = []
    if affected_ids:
        # Supplier-to-supplier links are not modelled yet (confirmed sub-tier
        # relationships arrive with the multi-tier map), so impact stays at tier 1.
        supplier_graph: Dict[str, List[Dict[str, Any]]] = {sid: [] for sid in org_suppliers}

        impacts = propagate_impact(
            event_id=event_id,
            initial_severity=event.get("severity", "high"),
            directly_affected_supplier_ids=affected_ids,
            supplier_graph=supplier_graph,
            supplier_info=org_suppliers,
        )
        for impact in impacts:
            impact["organization_id"] = org_id
        await store.add_impacts(org_id, impacts)

        # Auto-generate alerts for impacted suppliers
        event_alerts = []
        for impact in impacts:
            if impact["impact_severity"] in ("critical", "high"):
                event_alerts.append({
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "alert_type": "event_impact",
                    "severity": impact["impact_severity"],
                    "title": f"Impact from: {event.get('title', 'Unknown Event')}",
                    "description": f"{impact['impacted_entity_name']} affected (Tier {impact['tier_distance']}, est. {impact['estimated_disruption_days']}d disruption)",
                    "status": "active",
                    "metadata": {"event_id": event_id, "impact_id": impact["id"]},
                    "created_at": datetime.utcnow().isoformat(),
                })
        await store.add_alerts(org_id, event_alerts)

    return {"event": event, "impacts": impacts, "total_impacts": len(impacts)}


@app.get("/events")
async def list_risk_events(limit: int = 50, org_id: str = Depends(tenant_org)):
    """List all risk events."""
    events, total = await store.list_events(org_id, limit=limit)
    return {"events": events, "total": total}


@app.get("/events/{event_id}/impacts")
async def get_event_impacts(event_id: str, org_id: str = Depends(tenant_org)):
    """Get all impacts for a specific risk event."""
    impacts = await store.event_impacts(org_id, event_id)
    return {"event_id": event_id, "impacts": impacts, "total": len(impacts)}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("COORDINATOR_SERVICE_PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
