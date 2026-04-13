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
from typing import Any, Dict, Optional

import httpx
import structlog
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.models import (
    AssessmentStatus,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
)
from libs.common.monitoring import setup_monitoring, track_agent_task

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PLANNER_URL = os.getenv("PLANNER_SERVICE_URL", "http://localhost:8002")
RESEARCHER_URL = os.getenv("RESEARCHER_SERVICE_URL", "http://localhost:8003")
EXECUTOR_URL = os.getenv("EXECUTOR_SERVICE_URL", "http://localhost:8004")
REVIEWER_URL = os.getenv("REVIEWER_SERVICE_URL", "http://localhost:8005")
AGENT_TIMEOUT = float(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))
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
    yield
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_monitoring(app, service_name="coordinator")


# ---------------------------------------------------------------------------
# Helper: call a downstream agent
# ---------------------------------------------------------------------------

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

    # Extract risks from executor metadata (it identifies risks while generating recommendations)
    risks_raw = executor_result.get("metadata", {}).get("risks_identified", [])
    if isinstance(risks_raw, int):
        risks_raw = []
    recommendations_raw = executor_result.get("recommendations", [])

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
        risks=[],  # risks come from executor/researcher — will be populated when those agents return Risk objects
        recommendations=[],  # same — serialized Recommendation objects will flow through here
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


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("COORDINATOR_SERVICE_PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
