"""
SCIRM Risk Scorer Agent
Multi-dimensional risk scoring across 7 dimensions:
ESG, Cyber, Financial, Geopolitical, Catastrophic, Operational, Regulatory.
"""

import json
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
from libs.common.risk_rubrics import (
    RiskDimension,
    DIMENSION_LABELS,
    RUBRICS,
    compute_composite_score,
    get_llm_scoring_prompt,
)

logger = structlog.get_logger()

app = FastAPI(
    title="SCIRM Risk Scorer Agent",
    description="7-dimension risk scoring engine",
    version="1.0.0",
)

setup_cors(app)
setup_monitoring(app, service_name="risk-scorer")


class ScoreRequest(BaseModel):
    supplier_name: str
    supplier_context: Dict[str, Any] = {}
    dimensions: List[str] = []  # Empty = score all 7


class DimensionScore(BaseModel):
    dimension: str
    label: str
    score: float
    confidence: float
    trend: str
    reasoning: str
    key_factors: List[str] = []


class ScoreResponse(BaseModel):
    supplier_name: str
    dimension_scores: List[DimensionScore]
    composite_score: float
    assessed_at: str
    llm_enhanced: bool


async def _score_dimension(
    supplier_name: str,
    supplier_context: Dict[str, Any],
    dimension: RiskDimension,
) -> DimensionScore:
    """Score a single dimension using LLM or rule-based fallback."""
    if llm_client.is_configured():
        try:
            prompt = get_llm_scoring_prompt(supplier_name, supplier_context, dimension)
            result = await llm_client.generate_json(prompt)
            return DimensionScore(
                dimension=dimension.value,
                label=DIMENSION_LABELS[dimension],
                score=min(max(float(result.get("score", 50)), 0), 100),
                confidence=float(result.get("confidence", 0.5)),
                trend=result.get("trend", "stable"),
                reasoning=result.get("reasoning", ""),
                key_factors=result.get("key_factors", []),
            )
        except Exception as exc:
            logger.warning("LLM scoring failed, using rules", dimension=dimension.value, error=str(exc))

    # Rule-based fallback
    base_scores = {
        "esg": 45, "cyber": 55, "financial": 40, "geopolitical": 35,
        "catastrophic": 30, "operational": 50, "regulatory": 45,
    }
    country = supplier_context.get("country_code", "")
    risk_score = supplier_context.get("risk_score", 50)

    score = base_scores.get(dimension.value, 50)
    # Adjust by existing risk score
    score = score * 0.6 + risk_score * 0.4
    # Geographic adjustments
    high_risk_countries = {"CN", "RU", "IR", "VE", "KP"}
    if country in high_risk_countries:
        score = min(score + 20, 100)

    return DimensionScore(
        dimension=dimension.value,
        label=DIMENSION_LABELS[dimension],
        score=round(score, 1),
        confidence=0.4,
        trend="stable",
        reasoning=f"Rule-based estimate for {supplier_name} ({dimension.value})",
        key_factors=[],
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "risk-scorer", "dimensions": len(RiskDimension), "llm_configured": llm_client.is_configured()}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "risk-scorer"}


@app.post("/score", response_model=ScoreResponse)
async def score_supplier(request: ScoreRequest):
    """Score a supplier across all 7 risk dimensions."""
    dims_to_score = (
        [RiskDimension(d) for d in request.dimensions if d in [dim.value for dim in RiskDimension]]
        if request.dimensions
        else list(RiskDimension)
    )

    scores = []
    for dim in dims_to_score:
        score = await _score_dimension(request.supplier_name, request.supplier_context, dim)
        scores.append(score)

    composite = compute_composite_score({s.dimension: s.score for s in scores})

    return ScoreResponse(
        supplier_name=request.supplier_name,
        dimension_scores=scores,
        composite_score=composite,
        assessed_at=datetime.utcnow().isoformat(),
        llm_enhanced=llm_client.is_configured(),
    )


@app.get("/dimensions")
async def list_dimensions():
    """List all risk dimensions with their rubrics."""
    return {
        "dimensions": [
            {
                "id": dim.value,
                "label": DIMENSION_LABELS[dim],
                "description": RUBRICS[dim]["description"],
                "factors": RUBRICS[dim]["factors"],
            }
            for dim in RiskDimension
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("RISK_SCORER_SERVICE_PORT", "8006"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
