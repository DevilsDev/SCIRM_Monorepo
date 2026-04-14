"""Add supplier graph relationships, components, risk events, and event impacts.

Revision ID: 005
Revises: 004
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Supplier hierarchy ---
    op.add_column("suppliers", sa.Column("parent_supplier_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("suppliers", sa.Column("tier_level", sa.Integer, server_default="1"))

    # --- Supplier relationships ---
    rel_type = postgresql.ENUM(
        "direct_supplier", "sub_supplier", "logistics_provider", "raw_material_source",
        name="relationship_type", create_type=False,
    )
    rel_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "supplier_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("target_supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("relationship_type", rel_type, server_default="'direct_supplier'"),
        sa.Column("tier_level", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("discovered_by", sa.String(20), server_default="'manual'"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_supplier_rels_source", "supplier_relationships", ["source_supplier_id"])
    op.create_index("ix_supplier_rels_target", "supplier_relationships", ["target_supplier_id"])

    # --- Components ---
    op.create_table(
        "components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("part_number", sa.String(100), nullable=True),
        sa.Column("category", sa.String(100), server_default="'general'"),
        sa.Column("criticality", sa.String(20), server_default="'medium'"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )

    # --- Supplier-Component join ---
    op.create_table(
        "supplier_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("components.id"), nullable=False),
        sa.Column("is_primary_source", sa.Boolean, server_default="true"),
        sa.Column("lead_time_days", sa.Integer, nullable=True),
        sa.Column("unit_cost", sa.Float, nullable=True),
    )

    # --- Risk Events ---
    event_type = postgresql.ENUM(
        "natural_disaster", "geopolitical", "regulatory_change", "cyber_attack",
        "financial_distress", "quality_failure", "logistics_disruption",
        name="event_type_enum", create_type=False,
    )
    event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "risk_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, server_default="''"),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("affected_region", sa.String(255), nullable=True),
        sa.Column("location_lat", sa.Float, nullable=True),
        sa.Column("location_lng", sa.Float, nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), server_default="'active'"),
        sa.Column("detected_at", sa.DateTime, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
    )
    op.create_index("ix_risk_events_type", "risk_events", ["event_type"])
    op.create_index("ix_risk_events_severity", "risk_events", ["severity"])
    op.create_index("ix_risk_events_detected", "risk_events", ["detected_at"])

    # --- Event Impacts ---
    op.create_table(
        "event_impacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_events.id"), nullable=False),
        sa.Column("impacted_entity_type", sa.String(50), nullable=False),
        sa.Column("impacted_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("impact_severity", sa.String(20), nullable=False),
        sa.Column("estimated_disruption_days", sa.Integer, nullable=True),
        sa.Column("estimated_financial_impact", sa.Float, nullable=True),
        sa.Column("impact_path", postgresql.JSON, server_default="[]"),
        sa.Column("tier_distance", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()")),
    )
    op.create_index("ix_event_impacts_event", "event_impacts", ["event_id"])
    op.create_index("ix_event_impacts_entity", "event_impacts", ["impacted_entity_type", "impacted_entity_id"])


def downgrade() -> None:
    op.drop_table("event_impacts")
    op.drop_table("risk_events")
    op.drop_table("supplier_components")
    op.drop_table("components")
    op.drop_table("supplier_relationships")
    op.drop_column("suppliers", "tier_level")
    op.drop_column("suppliers", "parent_supplier_id")
    op.execute("DROP TYPE IF EXISTS event_type_enum")
    op.execute("DROP TYPE IF EXISTS relationship_type")
