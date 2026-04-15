"""
SCIRM Planner Agent
Context-Augmented Generation (CAG) agent for organizational context and priorities.
Uses LLM for nuanced context analysis when available, falls back to rule-based logic.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.models import ContextualInsight, Organization, RiskAssessmentRequest
from libs.common.monitoring import setup_monitoring, track_agent_task
from libs.common.security import setup_cors
from libs.common import llm as llm_client

logger = structlog.get_logger()

app = FastAPI(
    title="SCIRM Planner Agent",
    description="Context-Augmented Generation for organizational insights",
    version="1.0.0",
)

setup_cors(app)
setup_monitoring(app, "planner")


class ContextAnalysisRequest(BaseModel):
    request: Dict[str, Any]


class ContextAnalysisResponse(BaseModel):
    context_summary: str
    organizational_priorities: List[str]
    risk_tolerance: Dict[str, float]
    compliance_requirements: List[str]
    contextual_insights: List[ContextualInsight]
    reasoning: str
    confidence_score: float
    metadata: Dict[str, Any]


class PlannerAgent:
    def __init__(self):
        self.organization_profiles = self._load_organization_profiles()

    def _load_organization_profiles(self) -> Dict[str, Organization]:
        return {
            "pharma-corp": Organization(
                id="pharma-corp",
                name="PharmaCorp International",
                industry="pharmaceutical",
                supply_chain_profile={
                    "primary_suppliers": ["supplier-a", "supplier-b"],
                    "critical_materials": ["api-compounds", "excipients"],
                    "manufacturing_sites": ["usa-east", "europe-central"],
                    "distribution_channels": ["retail", "hospital", "online"],
                },
                risk_tolerance={
                    "financial": 0.3,
                    "operational": 0.2,
                    "regulatory": 0.1,
                    "reputational": 0.15,
                },
                compliance_requirements=["FDA", "EMA", "GMP", "GDP", "HIPAA"],
            ),
            "a0000000-0000-0000-0000-000000000001": Organization(
                id="a0000000-0000-0000-0000-000000000001",
                name="PharmaCorp International",
                industry="pharmaceutical",
                supply_chain_profile={
                    "primary_suppliers": ["supplier-alpha", "supplier-beta", "supplier-gamma"],
                    "critical_materials": ["api-compound-x", "excipient-y", "packaging-z"],
                    "manufacturing_sites": ["usa-east", "europe-central", "asia-pacific"],
                    "distribution_channels": ["retail", "hospital", "online", "government"],
                },
                risk_tolerance={
                    "financial": 0.3,
                    "operational": 0.2,
                    "regulatory": 0.1,
                    "reputational": 0.15,
                },
                compliance_requirements=["FDA", "EMA", "GMP", "GDP", "HIPAA", "SOC2"],
            ),
        }

    @track_agent_task("planner", "context_analysis")
    async def analyze_context(self, request: RiskAssessmentRequest) -> ContextAnalysisResponse:
        org_id = (request.context or {}).get("organization_id", "default-org")
        organization = self.organization_profiles.get(org_id)

        if not organization:
            organization = Organization(
                id=org_id,
                name="Default Organization",
                industry="general",
                supply_chain_profile={},
                risk_tolerance={"default": 0.5},
                compliance_requirements=[],
            )

        # Analyze entities (convert to dicts for uniform access)
        contextual_insights: List[ContextualInsight] = []
        for entity in request.entities:
            entity_dict = entity.model_dump() if hasattr(entity, 'model_dump') else (entity if isinstance(entity, dict) else {})
            insights = await self._analyze_entity_context(entity_dict, organization)
            contextual_insights.extend(insights)

        # Determine priorities (LLM-enhanced when available)
        priorities = await self._determine_priorities(request, organization, contextual_insights)

        context_summary = self._generate_context_summary(organization, request, contextual_insights, priorities)
        confidence_score = self._calculate_confidence(contextual_insights)
        reasoning = self._build_reasoning(organization, request, contextual_insights, priorities)

        return ContextAnalysisResponse(
            context_summary=context_summary,
            organizational_priorities=priorities,
            risk_tolerance=organization.risk_tolerance,
            compliance_requirements=organization.compliance_requirements,
            contextual_insights=contextual_insights,
            reasoning=reasoning,
            confidence_score=confidence_score,
            metadata={
                "organization_id": org_id,
                "industry": organization.industry,
                "analysis_timestamp": datetime.utcnow().isoformat(),
                "entities_analyzed": len(request.entities),
                "llm_enhanced": llm_client.is_configured(),
            },
        )

    async def _analyze_entity_context(self, entity: Dict, organization: Organization) -> List[ContextualInsight]:
        insights: List[ContextualInsight] = []

        if organization.industry == "pharmaceutical":
            insights.extend(await self._pharma_context_analysis(entity, organization))

        insights.extend(await self._general_context_analysis(entity, organization))
        return insights

    async def _pharma_context_analysis(self, entity: Dict, organization: Organization) -> List[ContextualInsight]:
        """Pharmaceutical context analysis — LLM-enhanced when available."""
        entity_type = entity.get("type", "")
        entity_name = entity.get("name", "")
        entity_location = entity.get("location", "")

        # Try LLM-powered analysis first
        if llm_client.is_configured():
            try:
                prompt = f"""Analyze this entity in the context of a pharmaceutical supply chain.

Entity: {entity_name} (type: {entity_type}, location: {entity_location})
Organization: {organization.name}
Primary suppliers: {organization.supply_chain_profile.get('primary_suppliers', [])}
Compliance requirements: {organization.compliance_requirements}
Critical materials: {organization.supply_chain_profile.get('critical_materials', [])}

Return a JSON object with key "insights" containing an array. Each insight:
{{
  "category": "supplier_criticality|regulatory_compliance|material_criticality|quality_risk",
  "insight": "<specific, actionable insight about this entity>",
  "relevance_score": <0.0-1.0>,
  "source": "llm_analysis"
}}

Generate 2-4 insights relevant to pharmaceutical supply chain risk. Be specific to this entity."""

                result = await llm_client.generate_json(prompt)
                return [ContextualInsight(**i) for i in result.get("insights", [])]
            except Exception as exc:
                logger.warning("LLM pharma analysis failed, using rules", error=str(exc))

        # Rule-based fallback
        insights: List[ContextualInsight] = []

        if entity_type == "supplier":
            if entity.get("id") in organization.supply_chain_profile.get("primary_suppliers", []):
                insights.append(ContextualInsight(
                    category="supplier_criticality",
                    insight=f"{entity_name} is a primary supplier with high business impact",
                    relevance_score=0.9,
                    source="organizational_profile",
                ))
            insights.append(ContextualInsight(
                category="regulatory_compliance",
                insight=f"Supplier {entity_name} must comply with FDA/EMA regulations",
                relevance_score=0.8,
                source="industry_requirements",
            ))

        elif entity_type == "product":
            if any(m in entity_name.lower() for m in ["api", "compound", "excipient"]):
                insights.append(ContextualInsight(
                    category="material_criticality",
                    insight=f"{entity_name} is a critical pharmaceutical material",
                    relevance_score=0.95,
                    source="industry_knowledge",
                ))

        return insights

    async def _general_context_analysis(self, entity: Dict, organization: Organization) -> List[ContextualInsight]:
        """General context analysis — LLM-enhanced when available."""
        entity_name = entity.get("name", "")
        entity_type = entity.get("type", "")
        location = entity.get("location")

        if llm_client.is_configured() and location:
            try:
                prompt = f"""Analyze supply chain risks for this entity based on its location and role.

Entity: {entity_name} (type: {entity_type}, location: {location})
Organization industry: {organization.industry}
Risk tolerance: {json.dumps(organization.risk_tolerance)}

Return a JSON object with key "insights" containing an array. Each insight:
{{
  "category": "geographic_risk|economic_risk|climate_risk|market_risk",
  "insight": "<specific risk insight for this location/entity>",
  "relevance_score": <0.0-1.0>,
  "source": "llm_analysis"
}}

Generate 1-3 insights about location-specific supply chain risks."""

                result = await llm_client.generate_json(prompt)
                return [ContextualInsight(**i) for i in result.get("insights", [])]
            except Exception as exc:
                logger.warning("LLM general analysis failed, using rules", error=str(exc))

        # Rule-based fallback
        insights: List[ContextualInsight] = []
        if location:
            insights.append(ContextualInsight(
                category="geographic_risk",
                insight=f"Entity located in {location} - assess regional risks",
                relevance_score=0.6,
                source="geographic_analysis",
            ))
        return insights

    async def _determine_priorities(
        self,
        request: RiskAssessmentRequest,
        organization: Organization,
        insights: List[ContextualInsight],
    ) -> List[str]:
        """Determine organizational priorities — LLM-enhanced when available."""
        if llm_client.is_configured() and insights:
            try:
                insights_summary = [
                    {"category": i.category, "insight": i.insight, "relevance": i.relevance_score}
                    for i in insights
                ]
                prompt = f"""Determine the top risk assessment priorities for this organization.

Organization: {organization.name} ({organization.industry})
Risk tolerance: {json.dumps(organization.risk_tolerance)}
Compliance requirements: {organization.compliance_requirements}
Entities being assessed: {len(request.entities)}
Time horizon: {request.time_horizon_days} days
Identified insights: {json.dumps(insights_summary)}

Return a JSON object with key "priorities" as an array of strings (max 10).
Order by importance. Consider the org's risk appetite, industry, and identified insights."""

                result = await llm_client.generate_json(prompt)
                priorities = result.get("priorities", [])
                if priorities:
                    return priorities[:10]
            except Exception as exc:
                logger.warning("LLM priority analysis failed, using rules", error=str(exc))

        # Rule-based fallback
        priorities: List[str] = []

        if organization.industry == "pharmaceutical":
            priorities.extend(["regulatory_compliance", "product_quality", "supply_continuity", "patient_safety"])

        risk_tolerance = organization.risk_tolerance
        if risk_tolerance.get("regulatory", 0.5) < 0.3:
            priorities.insert(0, "strict_compliance")
        if risk_tolerance.get("operational", 0.5) < 0.3:
            priorities.insert(0, "operational_continuity")

        high_categories = {i.category for i in insights if i.relevance_score > 0.8}
        for cat in high_categories:
            if cat not in priorities:
                priorities.append(cat)

        return priorities[:10]

    def _generate_context_summary(
        self, organization: Organization, request: RiskAssessmentRequest,
        insights: List[ContextualInsight], priorities: List[str],
    ) -> str:
        parts = [
            f"Organization: {organization.name} ({organization.industry} industry)",
            f"Assessment scope: {len(request.entities)} entities over {request.time_horizon_days} days",
            f"Key priorities: {', '.join(priorities[:5])}",
            f"Compliance requirements: {', '.join(organization.compliance_requirements[:3])}",
        ]
        high_insights = [i for i in insights if i.relevance_score > 0.8]
        if high_insights:
            parts.append(f"Critical insights: {len(high_insights)} high-relevance factors identified")
        return ". ".join(parts) + "."

    def _calculate_confidence(self, insights: List[ContextualInsight]) -> float:
        if not insights:
            return 0.5
        avg_relevance = sum(i.relevance_score for i in insights) / len(insights)
        coverage = min(len(insights) / 10, 1.0)
        return round((avg_relevance + coverage) / 2, 3)

    def _build_reasoning(
        self, organization: Organization, request: RiskAssessmentRequest,
        insights: List[ContextualInsight], priorities: List[str],
    ) -> str:
        parts = [
            f"Analyzed {organization.name} in {organization.industry} industry context",
            f"Identified {len(insights)} contextual insights across {len(request.entities)} entities",
            f"Prioritized {len(priorities)} organizational factors",
            f"Applied industry-specific knowledge and compliance requirements",
        ]
        if llm_client.is_configured():
            parts.append("Enhanced with LLM-powered contextual analysis")
        return ". ".join(parts) + "."


planner_agent = PlannerAgent()


@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": "planner", "llm_configured": llm_client.is_configured()}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "planner"}


@app.post("/analyze-context", response_model=ContextAnalysisResponse)
async def analyze_context(request: ContextAnalysisRequest):
    try:
        risk_request = RiskAssessmentRequest(**request.request)
        return await planner_agent.analyze_context(risk_request)
    except Exception as e:
        logger.error("Context analysis failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Context analysis failed: {str(e)}")


@app.get("/organizations/{org_id}")
async def get_organization_profile(org_id: str):
    organization = planner_agent.organization_profiles.get(org_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@app.get("/organizations")
async def list_organizations():
    return {"organizations": list(planner_agent.organization_profiles.keys())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PLANNER_SERVICE_PORT", 8002)),
        reload=True,
    )
