"""
SCIRM Digital Twin Simulator
Monte Carlo simulation engine for supply chain disruption scenarios.
Models supplier graph, propagates disruptions, estimates financial impact distributions.
"""

import math
import os
import random
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

logger = structlog.get_logger()

app = FastAPI(title="SCIRM Digital Twin Simulator", description="Monte Carlo supply chain simulation", version="1.0.0")
setup_cors(app)
setup_monitoring(app, service_name="simulator")

COORDINATOR_URL = os.getenv("COORDINATOR_SERVICE_URL", "http://localhost:8001")


class SimulationRequest(BaseModel):
    scenario_type: str = "supplier_disruption"
    disrupted_suppliers: List[str] = []
    severity: str = "high"
    duration_days: int = 30
    num_simulations: int = 1000
    description: str = ""


class SimulationResult(BaseModel):
    simulation_id: str
    scenario_type: str
    num_simulations: int
    disrupted_suppliers: List[str]

    # Financial impact distribution
    financial_impact_mean: float
    financial_impact_p5: float
    financial_impact_p50: float
    financial_impact_p95: float
    financial_impact_max: float

    # Recovery time distribution
    recovery_days_mean: float
    recovery_days_p5: float
    recovery_days_p50: float
    recovery_days_p95: float

    # Cascade metrics
    suppliers_affected_mean: float
    cascade_depth_max: int

    # Histogram data for visualization
    financial_histogram: List[Dict[str, Any]]
    recovery_histogram: List[Dict[str, Any]]

    # Recommendations
    mitigation_actions: List[Dict[str, Any]]
    timestamp: str


# Built-in supplier network for simulation
SUPPLIER_NETWORK = {
    "Supplier Alpha": {"risk_score": 35, "revenue_share": 0.25, "alternatives": 2, "lead_time": 14, "region": "North America"},
    "Supplier Beta": {"risk_score": 62, "revenue_share": 0.20, "alternatives": 1, "lead_time": 21, "region": "Europe"},
    "Supplier Gamma": {"risk_score": 78, "revenue_share": 0.30, "alternatives": 0, "lead_time": 35, "region": "Asia Pacific"},
    "Supplier Delta": {"risk_score": 28, "revenue_share": 0.15, "alternatives": 3, "lead_time": 10, "region": "Asia Pacific"},
    "Supplier Epsilon": {"risk_score": 55, "revenue_share": 0.10, "alternatives": 2, "lead_time": 18, "region": "North America"},
}

SEVERITY_MULTIPLIER = {"low": 0.3, "medium": 0.6, "high": 0.85, "critical": 1.0}


def _run_single_simulation(
    disrupted: List[str],
    severity: str,
    duration: int,
    base_revenue: float = 10_000_000,
) -> Dict[str, float]:
    """Run a single Monte Carlo simulation iteration."""
    sev_mult = SEVERITY_MULTIPLIER.get(severity, 0.7)

    total_financial_impact = 0.0
    total_recovery_days = 0
    suppliers_affected = 0
    max_cascade = 0

    for supplier_name in disrupted:
        info = SUPPLIER_NETWORK.get(supplier_name, {"risk_score": 50, "revenue_share": 0.1, "alternatives": 1, "lead_time": 20})

        # Randomize parameters with normal distribution
        risk_factor = min(max(random.gauss(info["risk_score"] / 100, 0.15), 0.05), 1.0)
        revenue_impact = info["revenue_share"] * base_revenue * sev_mult * risk_factor

        # Recovery time depends on alternatives and lead time
        alt_factor = max(0.3, 1.0 - info["alternatives"] * 0.2)
        recovery = int(random.gauss(info["lead_time"] * alt_factor * sev_mult, info["lead_time"] * 0.3))
        recovery = max(3, min(recovery, duration * 3))

        # Cascade: each disrupted supplier may cascade to 0-2 others
        cascade_prob = risk_factor * sev_mult * 0.4
        cascaded = 0
        if random.random() < cascade_prob:
            cascaded = random.randint(1, 2)
            revenue_impact *= (1 + cascaded * 0.15)

        total_financial_impact += revenue_impact
        total_recovery_days = max(total_recovery_days, recovery)
        suppliers_affected += 1 + cascaded
        max_cascade = max(max_cascade, cascaded + 1)

    # Add duration-based cost (daily operational overhead)
    daily_cost = total_financial_impact / max(duration, 1) * 0.05
    total_financial_impact += daily_cost * min(total_recovery_days, duration)

    return {
        "financial_impact": round(total_financial_impact, 2),
        "recovery_days": total_recovery_days,
        "suppliers_affected": suppliers_affected,
        "cascade_depth": max_cascade,
    }


def _build_histogram(values: List[float], bins: int = 20) -> List[Dict[str, Any]]:
    """Build histogram data for D3 visualization."""
    if not values:
        return []
    min_val = min(values)
    max_val = max(values)
    if min_val == max_val:
        return [{"bin_start": min_val, "bin_end": max_val, "count": len(values)}]

    bin_width = (max_val - min_val) / bins
    histogram = []
    for i in range(bins):
        bin_start = min_val + i * bin_width
        bin_end = bin_start + bin_width
        count = sum(1 for v in values if bin_start <= v < bin_end)
        histogram.append({"bin_start": round(bin_start, 2), "bin_end": round(bin_end, 2), "count": count})
    return histogram


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * p / 100)
    return sorted_v[min(idx, len(sorted_v) - 1)]


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "simulator", "network_size": len(SUPPLIER_NETWORK)}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "simulator"}


@app.post("/simulate", response_model=SimulationResult)
async def run_simulation(request: SimulationRequest):
    """Run Monte Carlo simulation for a supply chain disruption scenario."""
    if not request.disrupted_suppliers:
        raise HTTPException(status_code=400, detail="At least one disrupted supplier required")

    logger.info("Starting simulation", suppliers=request.disrupted_suppliers, num_sims=request.num_simulations)

    # Run simulations
    results = []
    for _ in range(request.num_simulations):
        result = _run_single_simulation(
            request.disrupted_suppliers, request.severity, request.duration_days,
        )
        results.append(result)

    financial_impacts = [r["financial_impact"] for r in results]
    recovery_days = [r["recovery_days"] for r in results]
    suppliers_affected = [r["suppliers_affected"] for r in results]

    # Generate mitigation recommendations
    mitigations = []
    for supplier in request.disrupted_suppliers:
        info = SUPPLIER_NETWORK.get(supplier, {})
        if info.get("alternatives", 0) == 0:
            mitigations.append({
                "action": f"Qualify alternative supplier for {supplier}",
                "priority": "critical",
                "rationale": "Single-source dependency — no alternatives available",
                "estimated_cost": 75000,
                "timeline_days": 90,
            })
        if info.get("risk_score", 50) > 60:
            mitigations.append({
                "action": f"Increase safety stock for {supplier} materials",
                "priority": "high",
                "rationale": f"High risk score ({info.get('risk_score')}), buffer needed",
                "estimated_cost": 50000,
                "timeline_days": 14,
            })
        mitigations.append({
            "action": f"Establish monitoring for {supplier} region",
            "priority": "medium",
            "rationale": f"Early warning system for {info.get('region', 'unknown')} region",
            "estimated_cost": 15000,
            "timeline_days": 7,
        })

    return SimulationResult(
        simulation_id=str(uuid.uuid4()),
        scenario_type=request.scenario_type,
        num_simulations=request.num_simulations,
        disrupted_suppliers=request.disrupted_suppliers,
        financial_impact_mean=round(sum(financial_impacts) / len(financial_impacts), 2),
        financial_impact_p5=round(_percentile(financial_impacts, 5), 2),
        financial_impact_p50=round(_percentile(financial_impacts, 50), 2),
        financial_impact_p95=round(_percentile(financial_impacts, 95), 2),
        financial_impact_max=round(max(financial_impacts), 2),
        recovery_days_mean=round(sum(recovery_days) / len(recovery_days), 1),
        recovery_days_p5=round(_percentile(recovery_days, 5), 1),
        recovery_days_p50=round(_percentile(recovery_days, 50), 1),
        recovery_days_p95=round(_percentile(recovery_days, 95), 1),
        suppliers_affected_mean=round(sum(suppliers_affected) / len(suppliers_affected), 1),
        cascade_depth_max=max(r["cascade_depth"] for r in results),
        financial_histogram=_build_histogram(financial_impacts),
        recovery_histogram=_build_histogram([float(d) for d in recovery_days]),
        mitigation_actions=mitigations,
        timestamp=datetime.utcnow().isoformat(),
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SIMULATOR_SERVICE_PORT", "8010"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
