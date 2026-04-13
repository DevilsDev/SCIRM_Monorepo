"""
SCIRM Executor Agent
Generates actionable risk mitigation recommendations based on context and research data.
Uses LLM for context-aware recommendations when available, falls back to templates.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.models import Recommendation, Risk, RiskAssessmentRequest, RiskSeverity
from libs.common.monitoring import setup_monitoring, track_agent_task
from libs.common.security import setup_cors
from libs.common import llm as llm_client

logger = structlog.get_logger()

app = FastAPI(
    title="SCIRM Executor Agent",
    description="Actionable risk mitigation recommendation engine",
    version="1.0.0",
)

setup_cors(app)
setup_monitoring(app, "executor")

class RecommendationRequest(BaseModel):
    """Request for generating recommendations."""
    request: Dict[str, Any]
    context: Dict[str, Any]
    research_data: Dict[str, Any]

class RecommendationResponse(BaseModel):
    """Response with generated recommendations."""
    recommendations: List[Recommendation]
    risk_mitigation_strategy: str
    priority_matrix: Dict[str, List[str]]
    estimated_total_cost: float
    implementation_timeline: Dict[str, int]
    reasoning: str
    confidence_score: float
    metadata: Dict[str, Any]

class ExecutorAgent:
    """Executor agent for generating actionable recommendations."""
    
    def __init__(self):
        self.recommendation_templates = self._load_recommendation_templates()
        self.cost_models = self._initialize_cost_models()
    
    def _load_recommendation_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load recommendation templates by risk category."""
        return {
            "supplier": {
                "diversification": {
                    "title": "Supplier Diversification",
                    "description": "Identify and qualify alternative suppliers to reduce dependency",
                    "action_type": "preventive",
                    "base_cost": 50000,
                    "timeline_days": 90,
                    "success_probability": 0.8
                },
                "monitoring": {
                    "title": "Enhanced Supplier Monitoring",
                    "description": "Implement real-time supplier performance monitoring",
                    "action_type": "monitoring",
                    "base_cost": 25000,
                    "timeline_days": 30,
                    "success_probability": 0.9
                }
            },
            "logistics": {
                "route_optimization": {
                    "title": "Alternative Route Planning",
                    "description": "Develop backup transportation routes and logistics partners",
                    "action_type": "preventive",
                    "base_cost": 30000,
                    "timeline_days": 45,
                    "success_probability": 0.85
                },
                "inventory_buffer": {
                    "title": "Strategic Inventory Buffers",
                    "description": "Increase safety stock for critical materials",
                    "action_type": "preventive",
                    "base_cost": 100000,
                    "timeline_days": 14,
                    "success_probability": 0.95
                }
            },
            "regulatory": {
                "compliance_audit": {
                    "title": "Compliance System Audit",
                    "description": "Comprehensive review of regulatory compliance procedures",
                    "action_type": "reactive",
                    "base_cost": 75000,
                    "timeline_days": 60,
                    "success_probability": 0.9
                },
                "regulatory_monitoring": {
                    "title": "Regulatory Change Monitoring",
                    "description": "Automated monitoring of regulatory updates and changes",
                    "action_type": "monitoring",
                    "base_cost": 15000,
                    "timeline_days": 21,
                    "success_probability": 0.85
                }
            },
            "quality": {
                "quality_assurance": {
                    "title": "Enhanced Quality Controls",
                    "description": "Implement additional quality checkpoints and testing",
                    "action_type": "preventive",
                    "base_cost": 40000,
                    "timeline_days": 30,
                    "success_probability": 0.9
                },
                "supplier_audit": {
                    "title": "Supplier Quality Audit",
                    "description": "On-site quality system audits for critical suppliers",
                    "action_type": "reactive",
                    "base_cost": 20000,
                    "timeline_days": 45,
                    "success_probability": 0.8
                }
            },
            "financial": {
                "hedging": {
                    "title": "Currency/Commodity Hedging",
                    "description": "Financial instruments to hedge against price volatility",
                    "action_type": "preventive",
                    "base_cost": 10000,
                    "timeline_days": 7,
                    "success_probability": 0.7
                },
                "contract_renegotiation": {
                    "title": "Contract Terms Renegotiation",
                    "description": "Renegotiate supplier contracts with risk-sharing clauses",
                    "action_type": "reactive",
                    "base_cost": 5000,
                    "timeline_days": 60,
                    "success_probability": 0.6
                }
            }
        }
    
    def _initialize_cost_models(self) -> Dict[str, callable]:
        """Initialize cost calculation models."""
        return {
            "pharmaceutical": lambda base_cost, entities: base_cost * (1 + len(entities) * 0.2),
            "manufacturing": lambda base_cost, entities: base_cost * (1 + len(entities) * 0.15),
            "general": lambda base_cost, entities: base_cost * (1 + len(entities) * 0.1)
        }
    
    @track_agent_task("executor", "recommendation_generation")
    async def generate_recommendations(self, 
                                     request: RiskAssessmentRequest,
                                     context: Dict[str, Any],
                                     research_data: Dict[str, Any]) -> RecommendationResponse:
        """Generate actionable recommendations based on context and research."""
        
        # Identify risks from research data
        identified_risks = self._extract_risks_from_research(research_data, request)
        
        # Generate recommendations for each risk
        recommendations = []
        for risk in identified_risks:
            risk_recommendations = await self._generate_risk_recommendations(risk, context, research_data)
            recommendations.extend(risk_recommendations)
        
        # Prioritize recommendations
        prioritized_recommendations = self._prioritize_recommendations(recommendations, context)
        
        # Create priority matrix
        priority_matrix = self._create_priority_matrix(prioritized_recommendations)
        
        # Calculate costs and timeline
        total_cost = sum(rec.estimated_cost or 0 for rec in prioritized_recommendations)
        implementation_timeline = self._create_implementation_timeline(prioritized_recommendations)
        
        # Generate overall strategy
        strategy = await self._generate_mitigation_strategy(prioritized_recommendations, context)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence(prioritized_recommendations, research_data)
        
        reasoning = self._build_reasoning(identified_risks, prioritized_recommendations, context)
        
        return RecommendationResponse(
            recommendations=prioritized_recommendations,
            risk_mitigation_strategy=strategy,
            priority_matrix=priority_matrix,
            estimated_total_cost=total_cost,
            implementation_timeline=implementation_timeline,
            reasoning=reasoning,
            confidence_score=confidence_score,
            metadata={
                "risks_identified": len(identified_risks),
                "recommendations_generated": len(prioritized_recommendations),
                "generation_timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def _extract_risks_from_research(self, research_data: Dict[str, Any], 
                                   request: RiskAssessmentRequest) -> List[Risk]:
        """Extract and synthesize risks from research findings."""
        risks = []
        findings = research_data.get("findings", [])
        
        for finding in findings:
            if finding.get("risk_level") in ["high", "medium"]:
                risk_category = finding.get("type", "general")
                
                # Create risk based on finding
                risk = Risk(
                    id=str(uuid4()),
                    title=f"{risk_category.replace('_', ' ').title()} Risk",
                    description=self._generate_risk_description(finding),
                    severity=self._map_risk_level_to_severity(finding.get("risk_level", "low")),
                    probability=self._estimate_probability(finding),
                    impact_score=self._estimate_impact(finding, request),
                    affected_entities=[entity.id for entity in request.entities],
                    risk_category=risk_category,
                    detected_at=datetime.utcnow(),
                    data_sources=[finding.get("source", "research_analysis")]
                )
                risks.append(risk)
        
        return risks
    
    def _generate_risk_description(self, finding: Dict[str, Any]) -> str:
        """Generate risk description from research finding."""
        insights = finding.get("key_insights", [])
        if insights:
            return f"Risk identified: {insights[0]}"
        return f"Risk detected in {finding.get('type', 'supply chain')} analysis"
    
    def _map_risk_level_to_severity(self, risk_level: str) -> RiskSeverity:
        """Map research risk level to severity enum."""
        mapping = {
            "low": RiskSeverity.LOW,
            "medium": RiskSeverity.MEDIUM,
            "high": RiskSeverity.HIGH,
            "critical": RiskSeverity.CRITICAL
        }
        return mapping.get(risk_level, RiskSeverity.MEDIUM)
    
    def _estimate_probability(self, finding: Dict[str, Any]) -> float:
        """Estimate risk probability from finding data."""
        risk_level = finding.get("risk_level", "low")
        base_probabilities = {
            "low": 0.2,
            "medium": 0.5,
            "high": 0.8,
            "critical": 0.9
        }
        return base_probabilities.get(risk_level, 0.5)
    
    def _estimate_impact(self, finding: Dict[str, Any], request: RiskAssessmentRequest) -> float:
        """Estimate risk impact score."""
        risk_level = finding.get("risk_level", "low")
        entity_count = len(request.entities)
        
        base_impacts = {
            "low": 3.0,
            "medium": 5.0,
            "high": 7.0,
            "critical": 9.0
        }
        
        base_impact = base_impacts.get(risk_level, 5.0)
        
        # Adjust for number of affected entities
        entity_multiplier = min(1 + (entity_count - 1) * 0.1, 1.5)
        
        return min(base_impact * entity_multiplier, 10.0)
    
    async def _generate_risk_recommendations(self, risk: Risk, context: Dict[str, Any],
                                             research_data: Dict[str, Any]) -> List[Recommendation]:
        """Generate recommendations for a specific risk — LLM-enhanced when available."""
        industry = context.get("industry", context.get("metadata", {}).get("industry", "general"))

        # Try LLM-powered generation first
        if llm_client.is_configured():
            try:
                findings_summary = json.dumps(research_data.get("findings", [])[:5], default=str)
                prompt = f"""Generate 3-5 specific, actionable risk mitigation recommendations.

Risk: {risk.title}
Description: {risk.description}
Severity: {risk.severity.value}, Probability: {risk.probability}, Impact: {risk.impact_score}
Category: {risk.risk_category}
Industry: {industry}
Compliance: {context.get('compliance_requirements', [])}
Related research: {findings_summary}

Return a JSON object with key "recommendations" as an array. Each recommendation:
{{
  "title": "<clear action title>",
  "description": "<specific implementation description, 1-2 sentences>",
  "action_type": "preventive|reactive|monitoring",
  "priority": "high|medium|low",
  "estimated_cost": <dollar amount>,
  "estimated_impact": <1.0-10.0>,
  "timeline_days": <integer>,
  "resources_required": ["<role1>", "<role2>"],
  "success_probability": <0.0-1.0>
}}

Tailor recommendations to {industry} industry. Be specific and realistic with costs and timelines."""

                result = await llm_client.generate_json(prompt)
                llm_recs = result.get("recommendations", [])
                if llm_recs:
                    return [
                        Recommendation(
                            id=str(uuid4()),
                            risk_id=risk.id,
                            **{k: v for k, v in rec.items() if k in Recommendation.model_fields},
                        )
                        for rec in llm_recs
                    ]
            except Exception as exc:
                logger.warning("LLM recommendation generation failed, using templates", error=str(exc))

        # Template-based fallback
        recommendations = []
        category = risk.risk_category
        templates = self.recommendation_templates.get(category, {})
        cost_model = self.cost_models.get(industry, self.cost_models["general"])

        for template_name, template in templates.items():
            base_cost = template["base_cost"]
            adjusted_cost = cost_model(base_cost, [risk.id])

            timeline_multiplier = 1.0
            if risk.severity == RiskSeverity.CRITICAL:
                timeline_multiplier = 0.5
            elif risk.severity == RiskSeverity.HIGH:
                timeline_multiplier = 0.7

            adjusted_timeline = int(template["timeline_days"] * timeline_multiplier)

            recommendation = Recommendation(
                id=str(uuid4()),
                risk_id=risk.id,
                title=template["title"],
                description=template["description"],
                action_type=template["action_type"],
                priority=self._determine_priority(risk, template),
                estimated_cost=adjusted_cost,
                estimated_impact=self._calculate_recommendation_impact(risk, template),
                timeline_days=adjusted_timeline,
                resources_required=self._determine_resources(template, industry),
                success_probability=template["success_probability"],
            )
            recommendations.append(recommendation)

        return recommendations
    
    def _determine_priority(self, risk: Risk, template: Dict[str, Any]) -> str:
        """Determine recommendation priority."""
        if risk.severity in [RiskSeverity.CRITICAL, RiskSeverity.HIGH]:
            return "high"
        elif risk.severity == RiskSeverity.MEDIUM:
            return "medium"
        else:
            return "low"
    
    def _calculate_recommendation_impact(self, risk: Risk, template: Dict[str, Any]) -> float:
        """Calculate expected impact of recommendation."""
        # Base impact on risk severity and template success probability
        severity_impact = {
            RiskSeverity.LOW: 3.0,
            RiskSeverity.MEDIUM: 5.0,
            RiskSeverity.HIGH: 7.0,
            RiskSeverity.CRITICAL: 9.0
        }
        
        base_impact = severity_impact.get(risk.severity, 5.0)
        success_factor = template["success_probability"]
        
        return base_impact * success_factor
    
    def _determine_resources(self, template: Dict[str, Any], industry: str) -> List[str]:
        """Determine required resources for recommendation."""
        base_resources = ["project_manager", "subject_matter_expert"]
        
        if template["action_type"] == "preventive":
            base_resources.append("implementation_team")
        
        if industry == "pharmaceutical":
            base_resources.append("regulatory_specialist")
        
        if template.get("base_cost", 0) > 50000:
            base_resources.append("executive_sponsor")
        
        return base_resources
    
    def _prioritize_recommendations(self, recommendations: List[Recommendation], 
                                  context: Dict[str, Any]) -> List[Recommendation]:
        """Prioritize recommendations based on context and impact."""
        
        def priority_score(rec: Recommendation) -> float:
            # Calculate priority score based on multiple factors
            priority_weights = {"high": 3.0, "medium": 2.0, "low": 1.0}
            priority_factor = priority_weights.get(rec.priority, 1.0)
            
            impact_factor = rec.estimated_impact / 10.0
            success_factor = rec.success_probability
            
            # Cost efficiency (impact per dollar)
            cost_efficiency = rec.estimated_impact / (rec.estimated_cost or 1) * 1000
            
            return priority_factor * impact_factor * success_factor + cost_efficiency
        
        # Sort by priority score (descending)
        return sorted(recommendations, key=priority_score, reverse=True)
    
    def _create_priority_matrix(self, recommendations: List[Recommendation]) -> Dict[str, List[str]]:
        """Create priority matrix for recommendations."""
        matrix = {"high": [], "medium": [], "low": []}
        
        for rec in recommendations:
            matrix[rec.priority].append(rec.title)
        
        return matrix
    
    def _create_implementation_timeline(self, recommendations: List[Recommendation]) -> Dict[str, int]:
        """Create implementation timeline."""
        timeline = {
            "immediate": 0,  # < 7 days
            "short_term": 0,  # 7-30 days
            "medium_term": 0,  # 30-90 days
            "long_term": 0  # > 90 days
        }
        
        for rec in recommendations:
            days = rec.timeline_days or 30
            
            if days < 7:
                timeline["immediate"] += 1
            elif days <= 30:
                timeline["short_term"] += 1
            elif days <= 90:
                timeline["medium_term"] += 1
            else:
                timeline["long_term"] += 1
        
        return timeline
    
    async def _generate_mitigation_strategy(self, recommendations: List[Recommendation],
                                            context: Dict[str, Any]) -> str:
        """Generate overall risk mitigation strategy — LLM-enhanced when available."""
        high_priority = [r for r in recommendations if r.priority == "high"]
        total_cost = sum(r.estimated_cost or 0 for r in recommendations)
        industry = context.get("industry", context.get("metadata", {}).get("industry", "general"))

        if llm_client.is_configured() and recommendations:
            try:
                rec_summary = [
                    {"title": r.title, "priority": r.priority, "cost": r.estimated_cost, "days": r.timeline_days}
                    for r in recommendations[:10]
                ]
                prompt = f"""Write a concise executive risk mitigation strategy summary (3-5 sentences).

Industry: {industry}
Recommendations: {json.dumps(rec_summary)}
Total investment: ${total_cost:,.0f}
High-priority actions: {len(high_priority)}

Focus on: phased approach, expected outcomes, and critical success factors.
Return a JSON object with key "strategy" as a string."""

                result = await llm_client.generate_json(prompt)
                strategy = result.get("strategy", "")
                if strategy:
                    return strategy
            except Exception as exc:
                logger.warning("LLM strategy generation failed, using template", error=str(exc))

        # Template fallback
        strategy_parts = [
            f"Comprehensive risk mitigation strategy with {len(recommendations)} recommendations",
            f"Immediate focus on {len(high_priority)} high-priority actions",
            f"Estimated total investment: ${total_cost:,.0f}",
            f"Expected risk reduction: {sum(r.estimated_impact for r in recommendations):.1f} points",
        ]
        if industry == "pharmaceutical":
            strategy_parts.append("Special emphasis on regulatory compliance and quality assurance")
        return ". ".join(strategy_parts) + "."
    
    def _calculate_confidence(self, recommendations: List[Recommendation], 
                            research_data: Dict[str, Any]) -> float:
        """Calculate confidence score for recommendations."""
        if not recommendations:
            return 0.0
        
        # Base confidence on research data quality and recommendation coverage
        research_confidence = research_data.get("confidence_score", 0.5)
        
        # Average success probability of recommendations
        avg_success_prob = sum(r.success_probability for r in recommendations) / len(recommendations)
        
        # Coverage factor (more recommendations = higher confidence)
        coverage_factor = min(len(recommendations) / 10, 1.0)
        
        return (research_confidence + avg_success_prob + coverage_factor) / 3
    
    def _build_reasoning(self, risks: List[Risk], recommendations: List[Recommendation], 
                        context: Dict[str, Any]) -> str:
        """Build reasoning trail for recommendation generation."""
        reasoning_parts = [
            f"Analyzed {len(risks)} identified risks from research data",
            f"Generated {len(recommendations)} actionable recommendations",
            f"Prioritized based on impact, feasibility, and organizational context",
            f"Considered {context.get('industry', 'general')} industry requirements",
            f"Balanced preventive, reactive, and monitoring approaches"
        ]
        
        return ". ".join(reasoning_parts) + "."

# Global executor agent instance
executor_agent = ExecutorAgent()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": "executor", "llm_configured": llm_client.is_configured()}

@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "executor"}

@app.post("/generate-recommendations", response_model=RecommendationResponse)
async def generate_recommendations(request: RecommendationRequest):
    """Generate actionable recommendations."""
    try:
        risk_request = RiskAssessmentRequest(**request.request)
        return await executor_agent.generate_recommendations(
            risk_request, request.context, request.research_data
        )
    except Exception as e:
        logger.error("Recommendation generation failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Recommendation generation failed: {str(e)}")

@app.get("/recommendations/{risk_id}")
async def get_recommendations_for_risk(risk_id: str):
    """Get recommendations for a specific risk."""
    # In production, this would query a database
    return {
        "risk_id": risk_id,
        "recommendations": [],
        "message": "Risk-specific recommendations would be retrieved from database"
    }

@app.get("/templates")
async def list_recommendation_templates():
    """List available recommendation templates."""
    return {
        "templates": executor_agent.recommendation_templates
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("EXECUTOR_SERVICE_PORT", 8004)),
        reload=os.getenv("RELOAD", "false").lower() == "true"
    )
