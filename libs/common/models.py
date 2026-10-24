"""
SCIRM Shared Pydantic Models
Domain models used across all services.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Enums ---

class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssessmentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    REJECTED = "rejected"


# --- Core Domain Models ---

class User(BaseModel):
    id: str
    email: str
    name: str
    roles: List[str] = ["user"]
    organization_id: str = "default-org"


class Organization(BaseModel):
    id: str
    name: str
    industry: str
    supply_chain_profile: Dict[str, Any] = {}
    risk_tolerance: Dict[str, float] = {}
    compliance_requirements: List[str] = []


class Risk(BaseModel):
    id: str
    title: str
    description: str
    severity: RiskSeverity
    probability: float = Field(ge=0.0, le=1.0)
    impact_score: float = Field(ge=1.0, le=10.0)
    affected_entities: List[str] = []
    risk_category: str = ""
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    predicted_occurrence: Optional[str] = None
    data_sources: List[str] = []


class Recommendation(BaseModel):
    id: str
    risk_id: str
    title: str
    description: str
    action_type: str = "preventive"
    priority: str = "medium"
    estimated_cost: Optional[float] = None
    estimated_impact: float = Field(ge=1.0, le=10.0, default=5.0)
    timeline_days: Optional[int] = None
    resources_required: List[str] = []
    success_probability: float = Field(ge=0.0, le=1.0, default=0.5)


class ContextualInsight(BaseModel):
    category: str
    insight: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    source: str = ""


class QualityIssue(BaseModel):
    id: str
    severity: str = "medium"
    category: str = "completeness"
    description: str = ""
    affected_item_id: str = ""
    affected_item_type: str = "risk"
    suggested_action: str = ""


# --- Request/Response Models ---

class Entity(BaseModel):
    id: str
    name: str
    type: str
    location: Optional[str] = None
    metadata: Dict[str, Any] = {}


class RiskAssessmentRequest(BaseModel):
    entities: List[Entity]
    assessment_type: Optional[str] = "comprehensive"
    time_horizon_days: Optional[int] = 30
    priority_factors: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None


class RiskAssessmentResponse(BaseModel):
    task_id: str
    status: AssessmentStatus = AssessmentStatus.COMPLETED
    risks: List[Risk] = []
    recommendations: List[Recommendation] = []
    confidence_score: float = 0.0
    reasoning_trail: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}


# --- Agent-Specific Request/Response Models ---

class ContextAnalysisRequest(BaseModel):
    request: Dict[str, Any]


class ContextAnalysisResponse(BaseModel):
    context_summary: str = ""
    organizational_priorities: List[str] = []
    risk_tolerance: Dict[str, float] = {}
    compliance_requirements: List[str] = []
    contextual_insights: List[ContextualInsight] = []
    reasoning: str = ""
    confidence_score: float = 0.0
    metadata: Dict[str, Any] = {}


class RecommendationRequest(BaseModel):
    request: Dict[str, Any]
    context: Dict[str, Any] = {}
    research_data: Dict[str, Any] = {}


class RecommendationResponse(BaseModel):
    recommendations: List[Recommendation] = []
    risk_mitigation_strategy: str = ""
    priority_matrix: Dict[str, List[str]] = {}
    estimated_total_cost: float = 0.0
    implementation_timeline: Dict[str, int] = {}
    reasoning: str = ""
    confidence_score: float = 0.0
    metadata: Dict[str, Any] = {}


class ReviewRequest(BaseModel):
    risks: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}
    research_data: Dict[str, Any] = {}


class ReviewResponse(BaseModel):
    overall_quality_score: float = 0.0
    quality_issues: List[QualityIssue] = []
    validation_results: Dict[str, Any] = {}
    compliance_check: Dict[str, Any] = {}
    recommendations_review: Dict[str, Any] = {}
    approval_status: str = "conditional"
    review_summary: str = ""
    reasoning: str = ""
    confidence_score: float = 0.0
    metadata: Dict[str, Any] = {}
