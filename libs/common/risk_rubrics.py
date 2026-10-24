"""
SCIRM Risk Dimension Rubrics
Scoring criteria for each of the 7 risk dimensions.
"""

from enum import Enum
from typing import Any, Dict, List


class RiskDimension(str, Enum):
    ESG = "esg"
    CYBER = "cyber"
    FINANCIAL = "financial"
    GEOPOLITICAL = "geopolitical"
    CATASTROPHIC = "catastrophic"
    OPERATIONAL = "operational"
    REGULATORY = "regulatory"


DIMENSION_LABELS = {
    RiskDimension.ESG: "Environmental, Social & Governance",
    RiskDimension.CYBER: "Cybersecurity",
    RiskDimension.FINANCIAL: "Financial Health",
    RiskDimension.GEOPOLITICAL: "Geopolitical",
    RiskDimension.CATASTROPHIC: "Catastrophic Events",
    RiskDimension.OPERATIONAL: "Operational",
    RiskDimension.REGULATORY: "Regulatory Compliance",
}

DIMENSION_WEIGHTS = {
    RiskDimension.ESG: 0.10,
    RiskDimension.CYBER: 0.12,
    RiskDimension.FINANCIAL: 0.18,
    RiskDimension.GEOPOLITICAL: 0.15,
    RiskDimension.CATASTROPHIC: 0.10,
    RiskDimension.OPERATIONAL: 0.20,
    RiskDimension.REGULATORY: 0.15,
}

RUBRICS: Dict[RiskDimension, Dict[str, Any]] = {
    RiskDimension.ESG: {
        "description": "Environmental impact, labor practices, governance transparency, sustainability commitments",
        "factors": ["carbon_emissions", "labor_violations", "board_diversity", "sustainability_certifications"],
        "high_risk_indicators": ["environmental violations", "forced labor allegations", "governance scandals", "no ESG reporting"],
        "low_risk_indicators": ["ISO 14001 certified", "UN Global Compact signatory", "transparent ESG reporting", "science-based targets"],
    },
    RiskDimension.CYBER: {
        "description": "Cybersecurity posture, data protection, incident history, infrastructure resilience",
        "factors": ["security_certifications", "breach_history", "data_protection", "infrastructure_maturity"],
        "high_risk_indicators": ["recent data breach", "no SOC2/ISO27001", "unpatched systems", "no incident response plan"],
        "low_risk_indicators": ["SOC2 Type II", "ISO 27001", "zero breaches", "regular pen testing", "SIEM deployed"],
    },
    RiskDimension.FINANCIAL: {
        "description": "Financial stability, credit rating, revenue trends, debt levels, payment history",
        "factors": ["credit_rating", "revenue_trend", "debt_ratio", "payment_history", "profitability"],
        "high_risk_indicators": ["declining revenue", "high debt ratio", "late payments", "credit downgrade", "bankruptcy risk"],
        "low_risk_indicators": ["investment grade rating", "growing revenue", "strong cash flow", "consistent payments"],
    },
    RiskDimension.GEOPOLITICAL: {
        "description": "Political stability, trade restrictions, sanctions, regional conflicts, tariff exposure",
        "factors": ["country_stability_index", "sanctions_exposure", "trade_restrictions", "conflict_proximity"],
        "high_risk_indicators": ["sanctioned country", "active conflict zone", "trade embargo", "political instability"],
        "low_risk_indicators": ["stable democracy", "trade agreement member", "no sanctions", "low corruption index"],
    },
    RiskDimension.CATASTROPHIC: {
        "description": "Natural disaster exposure, pandemic impact, climate vulnerability, black swan risk",
        "factors": ["natural_disaster_exposure", "climate_vulnerability", "pandemic_resilience", "single_point_of_failure"],
        "high_risk_indicators": ["hurricane zone", "earthquake zone", "flood plain", "single-site production", "no BCP"],
        "low_risk_indicators": ["multi-site operations", "disaster recovery plan", "geographic diversification", "insurance coverage"],
    },
    RiskDimension.OPERATIONAL: {
        "description": "Production capacity, quality metrics, delivery performance, workforce stability",
        "factors": ["capacity_utilization", "quality_defect_rate", "on_time_delivery", "workforce_turnover"],
        "high_risk_indicators": ["capacity constraints", "quality recalls", "delivery failures", "labor disputes", "key person dependency"],
        "low_risk_indicators": ["excess capacity", "Six Sigma certified", "99%+ OTD", "low turnover", "cross-trained workforce"],
    },
    RiskDimension.REGULATORY: {
        "description": "Regulatory compliance, audit results, certification status, enforcement actions",
        "factors": ["compliance_certifications", "audit_findings", "enforcement_actions", "regulatory_changes"],
        "high_risk_indicators": ["FDA warning letter", "compliance violations", "expired certifications", "pending enforcement"],
        "low_risk_indicators": ["clean audit history", "all certifications current", "proactive compliance", "regulatory partnerships"],
    },
}


def compute_composite_score(dimension_scores: Dict[str, float]) -> float:
    """Compute weighted composite risk score from individual dimensions."""
    total = 0.0
    weight_sum = 0.0
    for dim in RiskDimension:
        score = dimension_scores.get(dim.value, 50.0)
        weight = DIMENSION_WEIGHTS.get(dim, 1.0 / 7)
        total += score * weight
        weight_sum += weight
    return round(total / weight_sum if weight_sum else 50.0, 1)


def get_llm_scoring_prompt(supplier_name: str, supplier_context: Dict[str, Any], dimension: RiskDimension) -> str:
    """Generate LLM prompt for scoring a specific risk dimension."""
    rubric = RUBRICS[dimension]
    return f"""Score this supplier on the {DIMENSION_LABELS[dimension]} risk dimension.

Supplier: {supplier_name}
Context: {supplier_context}

Dimension: {dimension.value}
Description: {rubric['description']}
Key factors: {', '.join(rubric['factors'])}
High risk indicators: {', '.join(rubric['high_risk_indicators'])}
Low risk indicators: {', '.join(rubric['low_risk_indicators'])}

Return a JSON object:
{{
  "score": <0-100, where 0=no risk, 100=extreme risk>,
  "confidence": <0.0-1.0>,
  "trend": "improving|stable|deteriorating",
  "reasoning": "<1-2 sentence explanation>",
  "key_factors": ["<factor1>", "<factor2>"]
}}"""
