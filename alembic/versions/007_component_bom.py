"""Add component BOM (Bill of Materials) table.

Revision ID: 007
Revises: 006
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "component_bom",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=False),
        sa.Column("child_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=False),
        sa.Column("quantity", sa.Float, server_default="1"),
        sa.Column("is_critical", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_bom_parent", "component_bom", ["parent_component_id"])
    op.create_index("ix_bom_child", "component_bom", ["child_component_id"])


def downgrade() -> None:
    op.drop_table("component_bom")
