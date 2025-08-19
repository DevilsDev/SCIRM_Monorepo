"""
SCIRM Planner Agent
Context-Augmented Generation (CAG) agent for organizational context and priorities.
"""

import os
from datetime import datetime
from typing import Dict, List, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

from libs.common.models import RiskAssessmentRequest, ContextualInsight, Organization
from libs.common.monitoring import setup_monitoring, track_agent_task
from libs.cag.context_engine import ContextEngine

logger = structlog.get_logger()

app = FastAPI(
    title="SCIRM Planner Agent",
    description="Context-Augmented Generation for organizational insights",
    version="1.0.0"
)

setup_monitoring(app, "planner")

class ContextAnalysisRequest(BaseModel):
    """Request for context analysis."""
    request: Dict[str, Any]

class ContextAnalysisResponse(BaseModel):
    """Response from context analysis."""
    context_summary: str
    organizational_priorities: List[str]
    risk_tolerance: Dict[str, float]
    compliance_requirements: List[str]
    contextual_insights: List[ContextualInsight]
    reasoning: str
    confidence_score: float
    metadata: Dict[str, Any]

class PlannerAgent:
    """Planner agent implementing CAG for organizational context."""
    
    def __init__(self):
        self.context_engine = ContextEngine()
        self.organization_profiles = self._load_organization_profiles()
    
    def _load_organization_profiles(self) -> Dict[str, Organization]:
        """Load organization profiles for context."""
        # In production, this would load from database
        return {
            "pharma-corp": Organization(
                id="pharma-corp",
                name="PharmaCorp International",
                industry="pharmaceutical",
                supply_chain_profile={
                    "primary_suppliers": ["supplier-a", "supplier-b"],
                    "critical_materials": ["api-compounds", "excipients"],
                    "manufacturing_sites": ["usa-east", "europe-central"],
                    "distribution_channels": ["retail", "hospital", "online"]
                },
                risk_tolerance={
                    "financial": 0.3,
                    "operational": 0.2,
                    "regulatory": 0.1,
                    "reputational": 0.15
                },
                compliance_requirements=["FDA", "EMA", "GMP", "GDP", "HIPAA"]
            )
        }
    
    @track_agent_task("planner", "context_analysis")
    async def analyze_context(self, request: RiskAssessmentRequest) -> ContextAnalysisResponse:
        """Analyze organizational context for risk assessment."""
        
        # Extract organization context
        org_id = request.context.get("organization_id", "default-org")
        organization = self.organization_profiles.get(org_id)
        
        if not organization:
            # Create default organization context
            organization = Organization(
                id=org_id,
                name="Default Organization",
                industry="general",
                supply_chain_profile={},
                risk_tolerance={"default": 0.5},
                compliance_requirements=[]
            )
        
        # Analyze entities in context of organization
        contextual_insights = []
        organizational_priorities = []
        
        for entity in request.entities:
            insights = await self._analyze_entity_context(entity, organization)
            contextual_insights.extend(insights)
        
        # Determine organizational priorities based on context
        priorities = self._determine_priorities(request, organization, contextual_insights)
        organizational_priorities.extend(priorities)
        
        # Generate context summary
        context_summary = self._generate_context_summary(
            organization, request, contextual_insights, priorities
        )
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence(contextual_insights)
        
        reasoning = self._build_reasoning(
            organization, request, contextual_insights, priorities
        )
        
        return ContextAnalysisResponse(
            context_summary=context_summary,
            organizational_priorities=organizational_priorities,
            risk_tolerance=organization.risk_tolerance,
            compliance_requirements=organization.compliance_requirements,
            contextual_insights=contextual_insights,
            reasoning=reasoning,
            confidence_score=confidence_score,
            metadata={
                "organization_id": org_id,
                "industry": organization.industry,
                "analysis_timestamp": datetime.utcnow().isoformat(),
                "entities_analyzed": len(request.entities)
            }
        )
    
    async def _analyze_entity_context(self, entity: Dict, organization: Organization) -> List[ContextualInsight]:
        """Analyze individual entity in organizational context."""
        insights = []
        
        # Industry-specific context analysis
        if organization.industry == "pharmaceutical":
            insights.extend(self._pharma_context_analysis(entity, organization))
        
        # General supply chain context
        insights.extend(self._general_context_analysis(entity, organization))
        
        return insights
    
    def _pharma_context_analysis(self, entity: Dict, organization: Organization) -> List[ContextualInsight]:
        """Pharmaceutical industry specific context analysis."""
        insights = []
        
        entity_type = entity.get("type", "")
        entity_name = entity.get("name", "")
        
        if entity_type == "supplier":
            # Critical supplier analysis
            if entity.get("id") in organization.supply_chain_profile.get("primary_suppliers", []):
                insights.append(ContextualInsight(
                    category="supplier_criticality",
                    insight=f"{entity_name} is a primary supplier with high business impact",
                    relevance_score=0.9,
                    source="organizational_profile"
                ))
            
            # Regulatory compliance context
            insights.append(ContextualInsight(
                category="regulatory_compliance",
                insight=f"Supplier {entity_name} must comply with FDA/EMA regulations",
                relevance_score=0.8,
                source="industry_requirements"
            ))
        
        elif entity_type == "product":
            # Critical material analysis
            if any(material in entity_name.lower() for material in ["api", "compound", "excipient"]):
                insights.append(ContextualInsight(
                    category="material_criticality",
                    insight=f"{entity_name} is a critical pharmaceutical material",
                    relevance_score=0.95,
                    source="industry_knowledge"
                ))
        
        return insights
    
    def _general_context_analysis(self, entity: Dict, organization: Organization) -> List[ContextualInsight]:
        """General supply chain context analysis."""
        insights = []
        
        # Geographic risk context
        location = entity.get("location")
        if location:
            insights.append(ContextualInsight(
                category="geographic_risk",
                insight=f"Entity located in {location} - assess regional risks",
                relevance_score=0.6,
                source="geographic_analysis"
            ))
        
        return insights
    
    def _determine_priorities(self, request: RiskAssessmentRequest, 
                            organization: Organization, 
                            insights: List[ContextualInsight]) -> List[str]:
        """Determine organizational priorities for risk assessment."""
        priorities = []
        
        # Industry-specific priorities
        if organization.industry == "pharmaceutical":
            priorities.extend([
                "regulatory_compliance",
                "product_quality",
                "supply_continuity",
                "patient_safety"
            ])
        
        # Risk tolerance based priorities
        risk_tolerance = organization.risk_tolerance
        if risk_tolerance.get("regulatory", 0.5) < 0.3:
            priorities.insert(0, "strict_compliance")
        
        if risk_tolerance.get("operational", 0.5) < 0.3:
            priorities.insert(0, "operational_continuity")
        
        # Context-driven priorities
        high_relevance_categories = [
            insight.category for insight in insights 
            if insight.relevance_score > 0.8
        ]
        
        for category in set(high_relevance_categories):
            if category not in priorities:
                priorities.append(category)
        
        return priorities[:10]  # Limit to top 10 priorities
    
    def _generate_context_summary(self, organization: Organization, 
                                 request: RiskAssessmentRequest,
                                 insights: List[ContextualInsight],
                                 priorities: List[str]) -> str:
        """Generate human-readable context summary."""
        
        summary_parts = [
            f"Organization: {organization.name} ({organization.industry} industry)",
            f"Assessment scope: {len(request.entities)} entities over {request.time_horizon_days} days",
            f"Key priorities: {', '.join(priorities[:5])}",
            f"Compliance requirements: {', '.join(organization.compliance_requirements[:3])}"
        ]
        
        if insights:
            high_relevance_insights = [i for i in insights if i.relevance_score > 0.8]
            if high_relevance_insights:
                summary_parts.append(
                    f"Critical insights: {len(high_relevance_insights)} high-relevance factors identified"
                )
        
        return ". ".join(summary_parts) + "."
    
    def _calculate_confidence(self, insights: List[ContextualInsight]) -> float:
        """Calculate confidence score for context analysis."""
        if not insights:
            return 0.5
        
        avg_relevance = sum(insight.relevance_score for insight in insights) / len(insights)
        insight_coverage = min(len(insights) / 10, 1.0)  # Normalize to max 10 insights
        
        return (avg_relevance + insight_coverage) / 2
    
    def _build_reasoning(self, organization: Organization,
                        request: RiskAssessmentRequest,
                        insights: List[ContextualInsight],
                        priorities: List[str]) -> str:
        """Build reasoning trail for context analysis."""
        
        reasoning_parts = [
            f"Analyzed {organization.name} in {organization.industry} industry context",
            f"Identified {len(insights)} contextual insights across {len(request.entities)} entities",
            f"Prioritized {len(priorities)} organizational factors",
            f"Applied industry-specific knowledge and compliance requirements"
        ]
        
        return ". ".join(reasoning_parts) + "."

# Global planner agent instance
planner_agent = PlannerAgent()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "agent": "planner"}

@app.post("/analyze-context", response_model=ContextAnalysisResponse)
async def analyze_context(request: ContextAnalysisRequest):
    """Analyze organizational context for risk assessment."""
    try:
        risk_request = RiskAssessmentRequest(**request.request)
        return await planner_agent.analyze_context(risk_request)
    except Exception as e:
        logger.error("Context analysis failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Context analysis failed: {str(e)}")

@app.get("/organizations/{org_id}")
async def get_organization_profile(org_id: str):
    """Get organization profile."""
    organization = planner_agent.organization_profiles.get(org_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization

@app.get("/organizations")
async def list_organizations():
    """List available organizations."""
    return {
        "organizations": list(planner_agent.organization_profiles.keys())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PLANNER_SERVICE_PORT", 8002)),
        reload=os.getenv("RELOAD", "false").lower() == "true"
    )
