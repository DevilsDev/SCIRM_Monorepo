"""
SCIRM SQLAlchemy ORM Models
Database table definitions for all domain entities.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import relationship

from .database import Base


def gen_uuid():
    return uuid.uuid4()


# ---------- Organizations ----------

class OrganizationRow(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=False)
    supply_chain_profile = Column(JSON, default=dict)
    risk_tolerance = Column(JSON, default=dict)
    compliance_requirements = Column(ARRAY(String), default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("UserRow", back_populates="organization")
    assessments = relationship("RiskAssessmentRow", back_populates="organization")


# ---------- Users ----------

class UserRow(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    roles = Column(ARRAY(String), default=lambda: ["user"])
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    mfa_secret = Column(String(64), nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("OrganizationRow", back_populates="users")

    __table_args__ = (
        Index("ix_users_org", "organization_id"),
    )


# ---------- Risk Assessments (Task Tracking) ----------

class RiskAssessmentRow(Base):
    __tablename__ = "risk_assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(
        Enum("pending", "processing", "completed", "failed", name="assessment_status"),
        default="pending",
    )
    assessment_type = Column(String(50), default="comprehensive")
    request_payload = Column(JSON, default=dict)
    confidence_score = Column(Float, nullable=True)
    reasoning_trail = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("OrganizationRow", back_populates="assessments")
    risks = relationship("RiskRow", back_populates="assessment", cascade="all, delete-orphan")
    recommendations = relationship(
        "RecommendationRow", back_populates="assessment", cascade="all, delete-orphan"
    )
    review = relationship(
        "QualityReviewRow", back_populates="assessment", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_assessments_org_status", "organization_id", "status"),
        Index("ix_assessments_created", "created_at"),
    )


# ---------- Risks ----------

class RiskRow(Base):
    __tablename__ = "risks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("risk_assessments.id"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(
        Enum("low", "medium", "high", "critical", name="risk_severity"),
        nullable=False,
    )
    probability = Column(Float, nullable=False)
    impact_score = Column(Float, nullable=False)
    affected_entities = Column(ARRAY(String), default=list)
    risk_category = Column(String(100), default="")
    detected_at = Column(DateTime, default=datetime.utcnow)
    predicted_occurrence = Column(String(255), nullable=True)
    data_sources = Column(ARRAY(String), default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("RiskAssessmentRow", back_populates="risks")
    recommendations = relationship("RecommendationRow", back_populates="risk")

    __table_args__ = (
        Index("ix_risks_assessment", "assessment_id"),
        Index("ix_risks_severity", "severity"),
        Index("ix_risks_category", "risk_category"),
    )


# ---------- Recommendations ----------

class RecommendationRow(Base):
    __tablename__ = "recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("risk_assessments.id"), nullable=False)
    risk_id = Column(UUID(as_uuid=True), ForeignKey("risks.id"), nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    action_type = Column(String(50), default="preventive")
    priority = Column(String(20), default="medium")
    estimated_cost = Column(Float, nullable=True)
    estimated_impact = Column(Float, default=5.0)
    timeline_days = Column(Integer, nullable=True)
    resources_required = Column(ARRAY(String), default=list)
    success_probability = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("RiskAssessmentRow", back_populates="recommendations")
    risk = relationship("RiskRow", back_populates="recommendations")

    __table_args__ = (
        Index("ix_recommendations_assessment", "assessment_id"),
        Index("ix_recommendations_risk", "risk_id"),
        Index("ix_recommendations_priority", "priority"),
    )


# ---------- Quality Reviews ----------

class QualityReviewRow(Base):
    __tablename__ = "quality_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("risk_assessments.id"), unique=True, nullable=False)
    overall_quality_score = Column(Float, default=0.0)
    approval_status = Column(
        Enum("approved", "conditional", "rejected", name="approval_status"),
        default="conditional",
    )
    validation_results = Column(JSON, default=dict)
    compliance_check = Column(JSON, default=dict)
    recommendations_review = Column(JSON, default=dict)
    review_summary = Column(Text, default="")
    reasoning = Column(Text, default="")
    confidence_score = Column(Float, default=0.0)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("RiskAssessmentRow", back_populates="review")
    quality_issues = relationship(
        "QualityIssueRow", back_populates="review", cascade="all, delete-orphan"
    )


# ---------- Quality Issues ----------

class QualityIssueRow(Base):
    __tablename__ = "quality_issues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    review_id = Column(UUID(as_uuid=True), ForeignKey("quality_reviews.id"), nullable=False)
    severity = Column(String(20), default="medium")
    category = Column(String(50), default="completeness")
    description = Column(Text, default="")
    affected_item_id = Column(String(64), default="")
    affected_item_type = Column(String(20), default="risk")
    suggested_action = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    review = relationship("QualityReviewRow", back_populates="quality_issues")


# ---------- Audit Log ----------

class AuditLogRow(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(64), nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_audit_user", "user_id"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
        Index("ix_audit_created", "created_at"),
    )


# ---------- Suppliers ----------

class SupplierRow(Base):
    __tablename__ = "suppliers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    supplier_code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    supplier_type = Column(String(50), default="general")
    country_code = Column(String(3), nullable=True)
    region = Column(String(100), nullable=True)
    risk_score = Column(Float, default=50.0)
    risk_tier = Column(String(20), default="medium")
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    last_assessment_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------- Agent Telemetry ----------

class AgentRunRow(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("risk_assessments.id"), nullable=True)
    agent_type = Column(String(50), nullable=False)
    status = Column(String(20), default="running")
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    cost_usd = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    steps = relationship("AgentStepRow", back_populates="run", cascade="all, delete-orphan")


class AgentStepRow(Base):
    __tablename__ = "agent_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False)
    step_order = Column(Integer, nullable=False)
    step_type = Column(String(50), nullable=False)
    tool_name = Column(String(100), nullable=True)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    execution_time_ms = Column(Integer, nullable=True)
    token_count = Column(Integer, nullable=True)
    step_cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("AgentRunRow", back_populates="steps")


# ---------- Alerts ----------

class AlertRow(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    risk_id = Column(UUID(as_uuid=True), nullable=True)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="active")
    acknowledged_by = Column(UUID(as_uuid=True), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
