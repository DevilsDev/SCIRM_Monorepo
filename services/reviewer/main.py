"""
SCIRM Reviewer Agent
Quality validation and review of risk assessments and recommendations.
"""

import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

from libs.common.models import Risk, Recommendation, RiskSeverity
from libs.common.monitoring import setup_monitoring, track_agent_task

logger = structlog.get_logger()

app = FastAPI(
    title="SCIRM Reviewer Agent",
    description="Quality validation and review engine for risk assessments",
    version="1.0.0"
)

setup_monitoring(app, "reviewer")

class ReviewRequest(BaseModel):
    """Request for reviewing recommendations and assessments."""
    risks: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    context: Dict[str, Any]
    research_data: Dict[str, Any]

class QualityIssue(BaseModel):
    """Quality issue identified during review."""
    id: str
    severity: str  # critical, high, medium, low
    category: str  # completeness, accuracy, feasibility, compliance
    description: str
    affected_item_id: str
    affected_item_type: str  # risk, recommendation
    suggested_action: str

class ReviewResponse(BaseModel):
    """Response from quality review."""
    overall_quality_score: float
    quality_issues: List[QualityIssue]
    validation_results: Dict[str, Any]
    compliance_check: Dict[str, Any]
    recommendations_review: Dict[str, Any]
    approval_status: str  # approved, conditional, rejected
    review_summary: str
    reasoning: str
    confidence_score: float
    metadata: Dict[str, Any]

class ReviewerAgent:
    """Reviewer agent for quality validation and review."""
    
    def __init__(self):
        self.quality_criteria = self._initialize_quality_criteria()
        self.compliance_rules = self._initialize_compliance_rules()
        self.validation_thresholds = self._initialize_validation_thresholds()
    
    def _initialize_quality_criteria(self) -> Dict[str, Dict[str, Any]]:
        """Initialize quality criteria for different aspects."""
        return {
            "risk_assessment": {
                "completeness": {
                    "required_fields": ["title", "description", "severity", "probability", "impact_score"],
                    "min_description_length": 20,
                    "required_categories": ["supplier", "logistics", "regulatory", "quality", "financial"]
                },
                "accuracy": {
                    "severity_probability_alignment": True,
                    "impact_score_range": (1.0, 10.0),
                    "probability_range": (0.0, 1.0)
                },
                "consistency": {
                    "severity_impact_correlation": 0.7,
                    "data_source_reliability": 0.6
                }
            },
            "recommendations": {
                "completeness": {
                    "required_fields": ["title", "description", "action_type", "priority", "estimated_cost"],
                    "min_description_length": 30,
                    "required_resources": True
                },
                "feasibility": {
                    "max_cost_threshold": 1000000,
                    "max_timeline_days": 365,
                    "min_success_probability": 0.3
                },
                "effectiveness": {
                    "min_impact_score": 2.0,
                    "cost_effectiveness_ratio": 0.001  # impact per dollar
                }
            }
        }
    
    def _initialize_compliance_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize compliance validation rules."""
        return {
            "pharmaceutical": {
                "required_considerations": [
                    "FDA regulations",
                    "GMP compliance",
                    "Quality assurance",
                    "Regulatory reporting"
                ],
                "mandatory_reviews": ["regulatory_specialist", "quality_manager"],
                "documentation_requirements": ["audit_trail", "risk_register", "mitigation_plan"]
            },
            "healthcare": {
                "required_considerations": [
                    "HIPAA compliance",
                    "Patient safety",
                    "Medical device regulations"
                ],
                "mandatory_reviews": ["compliance_officer", "medical_director"],
                "documentation_requirements": ["privacy_impact", "safety_assessment"]
            },
            "general": {
                "required_considerations": [
                    "Business continuity",
                    "Stakeholder impact",
                    "Cost-benefit analysis"
                ],
                "mandatory_reviews": ["risk_manager"],
                "documentation_requirements": ["business_case", "implementation_plan"]
            }
        }
    
    def _initialize_validation_thresholds(self) -> Dict[str, float]:
        """Initialize validation score thresholds."""
        return {
            "approval_threshold": 0.8,
            "conditional_threshold": 0.6,
            "min_confidence_score": 0.5,
            "max_quality_issues_critical": 0,
            "max_quality_issues_high": 2
        }
    
    @track_agent_task("reviewer", "quality_review")
    async def review_assessment(self, 
                              risks: List[Dict[str, Any]],
                              recommendations: List[Dict[str, Any]],
                              context: Dict[str, Any],
                              research_data: Dict[str, Any]) -> ReviewResponse:
        """Perform comprehensive quality review of risk assessment and recommendations."""
        
        # Convert to domain objects for validation
        risk_objects = [self._dict_to_risk(risk_data) for risk_data in risks]
        recommendation_objects = [self._dict_to_recommendation(rec_data) for rec_data in recommendations]
        
        # Perform quality checks
        quality_issues = []
        
        # Review risks
        risk_issues = self._review_risks(risk_objects, context)
        quality_issues.extend(risk_issues)
        
        # Review recommendations
        recommendation_issues = self._review_recommendations(recommendation_objects, risk_objects, context)
        quality_issues.extend(recommendation_issues)
        
        # Validate consistency between risks and recommendations
        consistency_issues = self._validate_consistency(risk_objects, recommendation_objects)
        quality_issues.extend(consistency_issues)
        
        # Perform compliance checks
        compliance_results = self._check_compliance(risk_objects, recommendation_objects, context)
        
        # Calculate overall quality score
        quality_score = self._calculate_quality_score(quality_issues, compliance_results)
        
        # Determine approval status
        approval_status = self._determine_approval_status(quality_score, quality_issues)
        
        # Generate validation results
        validation_results = self._generate_validation_results(risk_objects, recommendation_objects)
        
        # Review recommendations in detail
        recommendations_review = self._detailed_recommendations_review(recommendation_objects, context)
        
        # Generate review summary
        review_summary = self._generate_review_summary(quality_score, quality_issues, approval_status)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(quality_issues, research_data)
        
        # Build reasoning
        reasoning = self._build_reasoning(quality_issues, compliance_results, validation_results)
        
        return ReviewResponse(
            overall_quality_score=quality_score,
            quality_issues=quality_issues,
            validation_results=validation_results,
            compliance_check=compliance_results,
            recommendations_review=recommendations_review,
            approval_status=approval_status,
            review_summary=review_summary,
            reasoning=reasoning,
            confidence_score=confidence_score,
            metadata={
                "risks_reviewed": len(risk_objects),
                "recommendations_reviewed": len(recommendation_objects),
                "issues_identified": len(quality_issues),
                "review_timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def _dict_to_risk(self, risk_data: Dict[str, Any]) -> Risk:
        """Convert dictionary to Risk object."""
        return Risk(
            id=risk_data.get("id", str(uuid4())),
            title=risk_data.get("title", ""),
            description=risk_data.get("description", ""),
            severity=RiskSeverity(risk_data.get("severity", "medium")),
            probability=risk_data.get("probability", 0.5),
            impact_score=risk_data.get("impact_score", 5.0),
            affected_entities=risk_data.get("affected_entities", []),
            risk_category=risk_data.get("risk_category", "general"),
            detected_at=datetime.fromisoformat(risk_data.get("detected_at", datetime.utcnow().isoformat())),
            data_sources=risk_data.get("data_sources", [])
        )
    
    def _dict_to_recommendation(self, rec_data: Dict[str, Any]) -> Recommendation:
        """Convert dictionary to Recommendation object."""
        return Recommendation(
            id=rec_data.get("id", str(uuid4())),
            risk_id=rec_data.get("risk_id", ""),
            title=rec_data.get("title", ""),
            description=rec_data.get("description", ""),
            action_type=rec_data.get("action_type", "preventive"),
            priority=rec_data.get("priority", "medium"),
            estimated_cost=rec_data.get("estimated_cost"),
            estimated_impact=rec_data.get("estimated_impact", 0.0),
            timeline_days=rec_data.get("timeline_days"),
            resources_required=rec_data.get("resources_required", []),
            success_probability=rec_data.get("success_probability", 0.5)
        )
    
    def _review_risks(self, risks: List[Risk], context: Dict[str, Any]) -> List[QualityIssue]:
        """Review risks for quality issues."""
        issues = []
        criteria = self.quality_criteria["risk_assessment"]
        
        for risk in risks:
            # Check completeness
            if len(risk.description) < criteria["completeness"]["min_description_length"]:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="medium",
                    category="completeness",
                    description=f"Risk description too brief (minimum {criteria['completeness']['min_description_length']} characters)",
                    affected_item_id=risk.id,
                    affected_item_type="risk",
                    suggested_action="Expand risk description with more details"
                ))
            
            # Check accuracy
            if not (criteria["accuracy"]["impact_score_range"][0] <= risk.impact_score <= criteria["accuracy"]["impact_score_range"][1]):
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="high",
                    category="accuracy",
                    description=f"Impact score {risk.impact_score} outside valid range {criteria['accuracy']['impact_score_range']}",
                    affected_item_id=risk.id,
                    affected_item_type="risk",
                    suggested_action="Adjust impact score to valid range"
                ))
            
            if not (criteria["accuracy"]["probability_range"][0] <= risk.probability <= criteria["accuracy"]["probability_range"][1]):
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="high",
                    category="accuracy",
                    description=f"Probability {risk.probability} outside valid range {criteria['accuracy']['probability_range']}",
                    affected_item_id=risk.id,
                    affected_item_type="risk",
                    suggested_action="Adjust probability to valid range"
                ))
            
            # Check severity-impact alignment
            severity_impact_expected = {
                RiskSeverity.LOW: (1.0, 4.0),
                RiskSeverity.MEDIUM: (3.0, 7.0),
                RiskSeverity.HIGH: (6.0, 9.0),
                RiskSeverity.CRITICAL: (8.0, 10.0)
            }
            
            expected_range = severity_impact_expected.get(risk.severity, (1.0, 10.0))
            if not (expected_range[0] <= risk.impact_score <= expected_range[1]):
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="medium",
                    category="consistency",
                    description=f"Impact score {risk.impact_score} inconsistent with severity {risk.severity.value}",
                    affected_item_id=risk.id,
                    affected_item_type="risk",
                    suggested_action="Align impact score with severity level"
                ))
        
        return issues
    
    def _review_recommendations(self, recommendations: List[Recommendation], 
                              risks: List[Risk], context: Dict[str, Any]) -> List[QualityIssue]:
        """Review recommendations for quality issues."""
        issues = []
        criteria = self.quality_criteria["recommendations"]
        
        for rec in recommendations:
            # Check completeness
            if len(rec.description) < criteria["completeness"]["min_description_length"]:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="medium",
                    category="completeness",
                    description=f"Recommendation description too brief (minimum {criteria['completeness']['min_description_length']} characters)",
                    affected_item_id=rec.id,
                    affected_item_type="recommendation",
                    suggested_action="Expand recommendation description"
                ))
            
            if not rec.resources_required:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="low",
                    category="completeness",
                    description="No resources specified for recommendation",
                    affected_item_id=rec.id,
                    affected_item_type="recommendation",
                    suggested_action="Specify required resources"
                ))
            
            # Check feasibility
            if rec.estimated_cost and rec.estimated_cost > criteria["feasibility"]["max_cost_threshold"]:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="high",
                    category="feasibility",
                    description=f"Estimated cost ${rec.estimated_cost:,.0f} exceeds threshold ${criteria['feasibility']['max_cost_threshold']:,.0f}",
                    affected_item_id=rec.id,
                    affected_item_type="recommendation",
                    suggested_action="Review cost estimate or break into smaller phases"
                ))
            
            if rec.timeline_days and rec.timeline_days > criteria["feasibility"]["max_timeline_days"]:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="medium",
                    category="feasibility",
                    description=f"Timeline {rec.timeline_days} days exceeds maximum {criteria['feasibility']['max_timeline_days']} days",
                    affected_item_id=rec.id,
                    affected_item_type="recommendation",
                    suggested_action="Reduce timeline or split into phases"
                ))
            
            if rec.success_probability < criteria["feasibility"]["min_success_probability"]:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="high",
                    category="feasibility",
                    description=f"Success probability {rec.success_probability:.2f} below minimum {criteria['feasibility']['min_success_probability']}",
                    affected_item_id=rec.id,
                    affected_item_type="recommendation",
                    suggested_action="Improve recommendation approach or provide alternatives"
                ))
            
            # Check effectiveness
            if rec.estimated_impact < criteria["effectiveness"]["min_impact_score"]:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="medium",
                    category="effectiveness",
                    description=f"Estimated impact {rec.estimated_impact:.1f} below minimum {criteria['effectiveness']['min_impact_score']}",
                    affected_item_id=rec.id,
                    affected_item_type="recommendation",
                    suggested_action="Enhance recommendation to increase impact"
                ))
            
            # Check cost-effectiveness
            if rec.estimated_cost and rec.estimated_cost > 0:
                cost_effectiveness = rec.estimated_impact / rec.estimated_cost
                if cost_effectiveness < criteria["effectiveness"]["cost_effectiveness_ratio"]:
                    issues.append(QualityIssue(
                        id=str(uuid4()),
                        severity="low",
                        category="effectiveness",
                        description=f"Cost-effectiveness ratio {cost_effectiveness:.6f} below threshold {criteria['effectiveness']['cost_effectiveness_ratio']}",
                        affected_item_id=rec.id,
                        affected_item_type="recommendation",
                        suggested_action="Optimize cost or enhance impact"
                    ))
        
        return issues
    
    def _validate_consistency(self, risks: List[Risk], recommendations: List[Recommendation]) -> List[QualityIssue]:
        """Validate consistency between risks and recommendations."""
        issues = []
        
        # Check if all high/critical risks have recommendations
        high_critical_risks = [r for r in risks if r.severity in [RiskSeverity.HIGH, RiskSeverity.CRITICAL]]
        
        for risk in high_critical_risks:
            risk_recommendations = [r for r in recommendations if r.risk_id == risk.id]
            if not risk_recommendations:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="critical",
                    category="completeness",
                    description=f"High/critical risk '{risk.title}' has no recommendations",
                    affected_item_id=risk.id,
                    affected_item_type="risk",
                    suggested_action="Generate recommendations for this risk"
                ))
        
        # Check for orphaned recommendations
        risk_ids = {r.id for r in risks}
        for rec in recommendations:
            if rec.risk_id not in risk_ids:
                issues.append(QualityIssue(
                    id=str(uuid4()),
                    severity="medium",
                    category="consistency",
                    description=f"Recommendation '{rec.title}' references non-existent risk {rec.risk_id}",
                    affected_item_id=rec.id,
                    affected_item_type="recommendation",
                    suggested_action="Link to valid risk or remove recommendation"
                ))
        
        return issues
    
    def _check_compliance(self, risks: List[Risk], recommendations: List[Recommendation], 
                         context: Dict[str, Any]) -> Dict[str, Any]:
        """Check compliance with industry regulations and standards."""
        industry = context.get("industry", "general")
        rules = self.compliance_rules.get(industry, self.compliance_rules["general"])
        
        compliance_results = {
            "industry": industry,
            "required_considerations_met": [],
            "missing_considerations": [],
            "mandatory_reviews_status": {},
            "documentation_compliance": {},
            "overall_compliance_score": 0.0
        }
        
        # Check required considerations
        all_descriptions = " ".join([r.description for r in risks] + [r.description for r in recommendations])
        
        for consideration in rules["required_considerations"]:
            if consideration.lower() in all_descriptions.lower():
                compliance_results["required_considerations_met"].append(consideration)
            else:
                compliance_results["missing_considerations"].append(consideration)
        
        # Calculate compliance score
        total_considerations = len(rules["required_considerations"])
        met_considerations = len(compliance_results["required_considerations_met"])
        compliance_results["overall_compliance_score"] = met_considerations / total_considerations if total_considerations > 0 else 1.0
        
        return compliance_results
    
    def _calculate_quality_score(self, quality_issues: List[QualityIssue], 
                               compliance_results: Dict[str, Any]) -> float:
        """Calculate overall quality score."""
        # Start with perfect score
        score = 1.0
        
        # Deduct points for quality issues
        severity_penalties = {
            "critical": 0.3,
            "high": 0.15,
            "medium": 0.05,
            "low": 0.02
        }
        
        for issue in quality_issues:
            penalty = severity_penalties.get(issue.severity, 0.02)
            score -= penalty
        
        # Factor in compliance score
        compliance_score = compliance_results.get("overall_compliance_score", 1.0)
        score = score * 0.7 + compliance_score * 0.3
        
        return max(0.0, min(1.0, score))
    
    def _determine_approval_status(self, quality_score: float, quality_issues: List[QualityIssue]) -> str:
        """Determine approval status based on quality score and issues."""
        critical_issues = [i for i in quality_issues if i.severity == "critical"]
        high_issues = [i for i in quality_issues if i.severity == "high"]
        
        if critical_issues or len(high_issues) > self.validation_thresholds["max_quality_issues_high"]:
            return "rejected"
        elif quality_score >= self.validation_thresholds["approval_threshold"]:
            return "approved"
        elif quality_score >= self.validation_thresholds["conditional_threshold"]:
            return "conditional"
        else:
            return "rejected"
    
    def _generate_validation_results(self, risks: List[Risk], recommendations: List[Recommendation]) -> Dict[str, Any]:
        """Generate detailed validation results."""
        return {
            "risks_validated": len(risks),
            "recommendations_validated": len(recommendations),
            "coverage_analysis": {
                "risk_categories_covered": len(set(r.risk_category for r in risks)),
                "action_types_covered": len(set(r.action_type for r in recommendations)),
                "priority_distribution": {
                    "high": len([r for r in recommendations if r.priority == "high"]),
                    "medium": len([r for r in recommendations if r.priority == "medium"]),
                    "low": len([r for r in recommendations if r.priority == "low"])
                }
            },
            "completeness_score": self._calculate_completeness_score(risks, recommendations),
            "consistency_score": self._calculate_consistency_score(risks, recommendations)
        }
    
    def _calculate_completeness_score(self, risks: List[Risk], recommendations: List[Recommendation]) -> float:
        """Calculate completeness score."""
        if not risks:
            return 0.0
        
        risks_with_recommendations = len(set(r.risk_id for r in recommendations))
        return risks_with_recommendations / len(risks)
    
    def _calculate_consistency_score(self, risks: List[Risk], recommendations: List[Recommendation]) -> float:
        """Calculate consistency score."""
        # Simple consistency metric based on severity-priority alignment
        aligned_recommendations = 0
        total_recommendations = len(recommendations)
        
        if total_recommendations == 0:
            return 1.0
        
        for rec in recommendations:
            # Find associated risk
            risk = next((r for r in risks if r.id == rec.risk_id), None)
            if risk:
                # Check if priority aligns with severity
                if ((risk.severity in [RiskSeverity.CRITICAL, RiskSeverity.HIGH] and rec.priority == "high") or
                    (risk.severity == RiskSeverity.MEDIUM and rec.priority in ["medium", "high"]) or
                    (risk.severity == RiskSeverity.LOW and rec.priority in ["low", "medium"])):
                    aligned_recommendations += 1
        
        return aligned_recommendations / total_recommendations
    
    def _detailed_recommendations_review(self, recommendations: List[Recommendation], 
                                       context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform detailed review of recommendations."""
        return {
            "total_recommendations": len(recommendations),
            "cost_analysis": {
                "total_cost": sum(r.estimated_cost or 0 for r in recommendations),
                "average_cost": sum(r.estimated_cost or 0 for r in recommendations) / len(recommendations) if recommendations else 0,
                "cost_distribution": self._analyze_cost_distribution(recommendations)
            },
            "timeline_analysis": {
                "average_timeline": sum(r.timeline_days or 0 for r in recommendations) / len(recommendations) if recommendations else 0,
                "timeline_distribution": self._analyze_timeline_distribution(recommendations)
            },
            "effectiveness_analysis": {
                "average_impact": sum(r.estimated_impact for r in recommendations) / len(recommendations) if recommendations else 0,
                "average_success_probability": sum(r.success_probability for r in recommendations) / len(recommendations) if recommendations else 0
            }
        }
    
    def _analyze_cost_distribution(self, recommendations: List[Recommendation]) -> Dict[str, int]:
        """Analyze cost distribution of recommendations."""
        distribution = {"low": 0, "medium": 0, "high": 0, "very_high": 0}
        
        for rec in recommendations:
            cost = rec.estimated_cost or 0
            if cost < 10000:
                distribution["low"] += 1
            elif cost < 50000:
                distribution["medium"] += 1
            elif cost < 200000:
                distribution["high"] += 1
            else:
                distribution["very_high"] += 1
        
        return distribution
    
    def _analyze_timeline_distribution(self, recommendations: List[Recommendation]) -> Dict[str, int]:
        """Analyze timeline distribution of recommendations."""
        distribution = {"immediate": 0, "short": 0, "medium": 0, "long": 0}
        
        for rec in recommendations:
            days = rec.timeline_days or 30
            if days < 7:
                distribution["immediate"] += 1
            elif days < 30:
                distribution["short"] += 1
            elif days < 90:
                distribution["medium"] += 1
            else:
                distribution["long"] += 1
        
        return distribution
    
    def _generate_review_summary(self, quality_score: float, quality_issues: List[QualityIssue], 
                               approval_status: str) -> str:
        """Generate human-readable review summary."""
        summary_parts = [
            f"Quality assessment completed with overall score of {quality_score:.2f}",
            f"Status: {approval_status.upper()}",
            f"Identified {len(quality_issues)} quality issues"
        ]
        
        if quality_issues:
            severity_counts = {}
            for issue in quality_issues:
                severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
            
            severity_summary = ", ".join([f"{count} {severity}" for severity, count in severity_counts.items()])
            summary_parts.append(f"Issues breakdown: {severity_summary}")
        
        return ". ".join(summary_parts) + "."
    
    def _calculate_confidence_score(self, quality_issues: List[QualityIssue], 
                                  research_data: Dict[str, Any]) -> float:
        """Calculate confidence score for the review."""
        # Base confidence on research data quality
        research_confidence = research_data.get("confidence_score", 0.5)
        
        # Adjust based on quality issues
        issue_impact = len([i for i in quality_issues if i.severity in ["critical", "high"]]) * 0.1
        
        confidence = research_confidence - issue_impact
        return max(0.0, min(1.0, confidence))
    
    def _build_reasoning(self, quality_issues: List[QualityIssue], 
                        compliance_results: Dict[str, Any],
                        validation_results: Dict[str, Any]) -> str:
        """Build reasoning trail for the review."""
        reasoning_parts = [
            f"Conducted comprehensive quality review using established criteria",
            f"Validated completeness, accuracy, feasibility, and effectiveness",
            f"Checked compliance with {compliance_results['industry']} industry standards",
            f"Identified {len(quality_issues)} areas for improvement",
            f"Coverage analysis shows {validation_results['completeness_score']:.1%} risk coverage"
        ]
        
        return ". ".join(reasoning_parts) + "."

# Global reviewer agent instance
reviewer_agent = ReviewerAgent()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "agent": "reviewer"}

@app.post("/review", response_model=ReviewResponse)
async def review_assessment(request: ReviewRequest):
    """Perform quality review of risk assessment and recommendations."""
    try:
        return await reviewer_agent.review_assessment(
            request.risks, request.recommendations, request.context, request.research_data
        )
    except Exception as e:
        logger.error("Review failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")

@app.get("/criteria")
async def get_quality_criteria():
    """Get quality criteria and validation rules."""
    return {
        "quality_criteria": reviewer_agent.quality_criteria,
        "compliance_rules": reviewer_agent.compliance_rules,
        "validation_thresholds": reviewer_agent.validation_thresholds
    }

@app.get("/compliance/{industry}")
async def get_compliance_rules(industry: str):
    """Get compliance rules for specific industry."""
    rules = reviewer_agent.compliance_rules.get(industry)
    if not rules:
        raise HTTPException(status_code=404, detail=f"Compliance rules not found for industry: {industry}")
    
    return {"industry": industry, "rules": rules}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("REVIEWER_SERVICE_PORT", 8005)),
        reload=os.getenv("RELOAD", "false").lower() == "true"
    )
