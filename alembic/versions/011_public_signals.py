"""Public intelligence signals (FDA recalls and shortages, GDACS disasters).

These tables deliberately have no row-level security. They hold public records
that every tenant may read, and no tenant data: matching signals to a tenant's
suppliers happens at query time, inside that tenant's RLS scope.

Revision ID: 011
Revises: 010
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "public_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("entity_names", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        # First distinctive token of each company name (libs/intel/matching.py), for candidate lookup.
        sa.Column("entity_keys", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("country_codes", postgresql.ARRAY(sa.String(3)), nullable=False, server_default="{}"),
        # When the event happened vs. when it became public. Point-in-time logic uses published_at.
        sa.Column("occurred_at", sa.Date, nullable=True),
        sa.Column("published_at", sa.Date, nullable=False),
        sa.Column("updated_at", sa.Date, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("raw", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source", "external_id", name="uq_public_signals_source_external"),
    )
    op.create_index("ix_public_signals_published", "public_signals", ["published_at"])
    op.execute("CREATE INDEX ix_public_signals_entity_keys ON public_signals USING gin (entity_keys)")
    op.execute("CREATE INDEX ix_public_signals_countries ON public_signals USING gin (country_codes)")

    op.create_table(
        "public_sources",
        sa.Column("source", sa.String(50), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),  # ok | error | rate_limited
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("signals_seen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("signals_new", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("public_sources")
    op.drop_table("public_signals")
