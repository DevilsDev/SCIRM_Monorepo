"""Add suppliers, agent telemetry, RAG persistence, and alerts tables.

Revision ID: 002
Revises: 001
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Suppliers ---
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("supplier_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("supplier_type", sa.String(50), default="general"),
        sa.Column("country_code", sa.String(3), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("risk_score", sa.Float, server_default="50.0"),
        sa.Column("risk_tier", sa.String(20), server_default="'medium'"),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("last_assessment_at", sa.DateTime, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "supplier_code", name="uq_supplier_org_code"),
    )
    op.create_index("ix_suppliers_org", "suppliers", ["organization_id"])
    op.create_index("ix_suppliers_risk_score", "suppliers", ["risk_score"])
    op.create_index("ix_suppliers_risk_tier", "suppliers", ["risk_tier"])

    # --- Agent Telemetry: Runs ---
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_assessments.id"), nullable=True),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="'running'"),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("cost_usd", sa.Float, server_default="0.0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_agent_runs_assessment", "agent_runs", ["assessment_id"])
    op.create_index("ix_agent_runs_agent_type", "agent_runs", ["agent_type"])
    op.create_index("ix_agent_runs_started", "agent_runs", ["started_at"])

    # --- Agent Telemetry: Steps ---
    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("step_type", sa.String(50), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("input_data", postgresql.JSON, server_default="{}"),
        sa.Column("output_data", postgresql.JSON, server_default="{}"),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("step_cost_usd", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_steps_run", "agent_steps", ["run_id"])

    # --- RAG Collections ---
    op.create_table(
        "rag_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("collection_name", sa.String(255), nullable=False),
        sa.Column("collection_type", sa.String(50), server_default="'general'"),
        sa.Column("embedding_model", sa.String(100), server_default="'text-embedding-3-small'"),
        sa.Column("vector_dimensions", sa.Integer, server_default="1536"),
        sa.Column("document_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("now()")),
    )

    # --- RAG Documents ---
    op.create_table(
        "rag_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_collections.id"), nullable=False),
        sa.Column("document_name", sa.String(500), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("processing_status", sa.String(20), server_default="'pending'"),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_rag_docs_collection", "rag_documents", ["collection_id"])

    # --- RAG Chunks ---
    op.create_table(
        "rag_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_documents.id"), nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_order", sa.Integer, nullable=False),
        sa.Column("chunk_metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_rag_chunks_doc", "rag_chunks", ["document_id"])

    # --- Alerts ---
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("status", sa.String(20), server_default="'active'"),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime, nullable=True),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_alerts_org", "alerts", ["organization_id"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_created", "alerts", ["created_at"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("rag_chunks")
    op.drop_table("rag_documents")
    op.drop_table("rag_collections")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
    op.drop_table("suppliers")
