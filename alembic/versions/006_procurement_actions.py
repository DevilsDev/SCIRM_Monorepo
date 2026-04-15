"""Add procurement actions table.

Revision ID: 006
Revises: 005
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "procurement_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("trigger_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_risk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, server_default="''"),
        sa.Column("status", sa.String(20), server_default="'proposed'"),
        sa.Column("current_supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposed_supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposed_supplier_name", sa.String(255), nullable=True),
        sa.Column("estimated_savings", sa.Float, server_default="0"),
        sa.Column("risk_reduction", sa.Float, server_default="0"),
        sa.Column("requires_approval", sa.Boolean, server_default="true"),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("executed_at", sa.DateTime, nullable=True),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_procurement_org", "procurement_actions", ["organization_id"])
    op.create_index("ix_procurement_status", "procurement_actions", ["status"])


def downgrade() -> None:
    op.drop_table("procurement_actions")
