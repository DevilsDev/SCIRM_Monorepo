"""Initial schema — organizations, users, assessments, risks, recommendations, reviews, audit log.

Revision ID: 001
Revises: None
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums ---
    assessment_status = postgresql.ENUM(
        "pending", "processing", "completed", "failed", name="assessment_status", create_type=False
    )
    risk_severity = postgresql.ENUM(
        "low", "medium", "high", "critical", name="risk_severity", create_type=False
    )
    approval_status = postgresql.ENUM(
        "approved", "conditional", "rejected", name="approval_status", create_type=False
    )
    assessment_status.create(op.get_bind(), checkfirst=True)
    risk_severity.create(op.get_bind(), checkfirst=True)
    approval_status.create(op.get_bind(), checkfirst=True)

    # --- Organizations ---
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("supply_chain_profile", postgresql.JSON, server_default="{}"),
        sa.Column("risk_tolerance", postgresql.JSON, server_default="{}"),
        sa.Column("compliance_requirements", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("now()")),
    )

    # --- Users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("roles", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_org", "users", ["organization_id"])

    # --- Risk Assessments ---
    op.create_table(
        "risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", sa.String(64), unique=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", assessment_status, server_default="pending"),
        sa.Column("assessment_type", sa.String(50), server_default="'comprehensive'"),
        sa.Column("request_payload", postgresql.JSON, server_default="{}"),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("reasoning_trail", postgresql.JSON, server_default="[]"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_assessments_task_id", "risk_assessments", ["task_id"])
    op.create_index("ix_assessments_org_status", "risk_assessments", ["organization_id", "status"])
    op.create_index("ix_assessments_created", "risk_assessments", ["created_at"])

    # --- Risks ---
    op.create_table(
        "risks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_assessments.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", risk_severity, nullable=False),
        sa.Column("probability", sa.Float, nullable=False),
        sa.Column("impact_score", sa.Float, nullable=False),
        sa.Column("affected_entities", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("risk_category", sa.String(100), server_default="''"),
        sa.Column("detected_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("predicted_occurrence", sa.String(255), nullable=True),
        sa.Column("data_sources", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_risks_assessment", "risks", ["assessment_id"])
    op.create_index("ix_risks_severity", "risks", ["severity"])
    op.create_index("ix_risks_category", "risks", ["risk_category"])

    # --- Recommendations ---
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_assessments.id"), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risks.id"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("action_type", sa.String(50), server_default="'preventive'"),
        sa.Column("priority", sa.String(20), server_default="'medium'"),
        sa.Column("estimated_cost", sa.Float, nullable=True),
        sa.Column("estimated_impact", sa.Float, server_default="5.0"),
        sa.Column("timeline_days", sa.Integer, nullable=True),
        sa.Column("resources_required", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("success_probability", sa.Float, server_default="0.5"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_recommendations_assessment", "recommendations", ["assessment_id"])
    op.create_index("ix_recommendations_risk", "recommendations", ["risk_id"])
    op.create_index("ix_recommendations_priority", "recommendations", ["priority"])

    # --- Quality Reviews ---
    op.create_table(
        "quality_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_assessments.id"), unique=True, nullable=False),
        sa.Column("overall_quality_score", sa.Float, server_default="0.0"),
        sa.Column("approval_status", approval_status, server_default="'conditional'"),
        sa.Column("validation_results", postgresql.JSON, server_default="{}"),
        sa.Column("compliance_check", postgresql.JSON, server_default="{}"),
        sa.Column("recommendations_review", postgresql.JSON, server_default="{}"),
        sa.Column("review_summary", sa.Text, server_default="''"),
        sa.Column("reasoning", sa.Text, server_default="''"),
        sa.Column("confidence_score", sa.Float, server_default="0.0"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )

    # --- Quality Issues ---
    op.create_table(
        "quality_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quality_reviews.id"), nullable=False),
        sa.Column("severity", sa.String(20), server_default="'medium'"),
        sa.Column("category", sa.String(50), server_default="'completeness'"),
        sa.Column("description", sa.Text, server_default="''"),
        sa.Column("affected_item_id", sa.String(64), server_default="''"),
        sa.Column("affected_item_type", sa.String(20), server_default="'risk'"),
        sa.Column("suggested_action", sa.Text, server_default="''"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )

    # --- Audit Log ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSON, server_default="{}"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_user", "audit_logs", ["user_id"])
    op.create_index("ix_audit_action", "audit_logs", ["action"])
    op.create_index("ix_audit_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_created", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("quality_issues")
    op.drop_table("quality_reviews")
    op.drop_table("recommendations")
    op.drop_table("risks")
    op.drop_table("risk_assessments")
    op.drop_table("users")
    op.drop_table("organizations")

    op.execute("DROP TYPE IF EXISTS approval_status")
    op.execute("DROP TYPE IF EXISTS risk_severity")
    op.execute("DROP TYPE IF EXISTS assessment_status")
