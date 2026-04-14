"""Add multi-dimensional risk scoring tables.

Revision ID: 004
Revises: 003
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Risk dimension enum
    dimension_enum = postgresql.ENUM(
        "esg", "cyber", "financial", "geopolitical", "catastrophic", "operational", "regulatory",
        name="risk_dimension", create_type=False,
    )
    dimension_enum.create(op.get_bind(), checkfirst=True)

    trend_enum = postgresql.ENUM(
        "improving", "stable", "deteriorating", name="risk_trend", create_type=False,
    )
    trend_enum.create(op.get_bind(), checkfirst=True)

    # Per-risk dimensional scores
    op.create_table(
        "risk_dimensions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risks.id"), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("dimension", dimension_enum, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, server_default="0.5"),
        sa.Column("trend", trend_enum, server_default="'stable'"),
        sa.Column("data_sources", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("reasoning", sa.Text, server_default="''"),
        sa.Column("assessed_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
    )
    op.create_index("ix_risk_dims_risk", "risk_dimensions", ["risk_id"])
    op.create_index("ix_risk_dims_supplier", "risk_dimensions", ["supplier_id"])
    op.create_index("ix_risk_dims_dimension", "risk_dimensions", ["dimension"])

    # Composite scores on suppliers
    op.add_column("suppliers", sa.Column("composite_risk_score", sa.Float, server_default="50.0"))
    op.add_column("suppliers", sa.Column("risk_dimensions_summary", postgresql.JSON, server_default="{}"))


def downgrade() -> None:
    op.drop_column("suppliers", "risk_dimensions_summary")
    op.drop_column("suppliers", "composite_risk_score")
    op.drop_table("risk_dimensions")
    op.execute("DROP TYPE IF EXISTS risk_trend")
    op.execute("DROP TYPE IF EXISTS risk_dimension")
