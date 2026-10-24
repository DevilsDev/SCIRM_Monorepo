"""Extend Row-Level Security to the tenant tables added in 004–007.

Revision ID: 008
Revises: 007
Create Date: 2026-10-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# scirm_current_org() is created in 003; see it for how the tenant is set.
DIRECT_ORG_TABLES = ["components", "risk_events", "procurement_actions"]

CHILD_TABLE_POLICIES = {
    # A dimension may hang off a risk, a supplier, or both; it is visible if either is.
    "risk_dimensions": (
        "(risk_id IS NOT NULL AND EXISTS (SELECT 1 FROM risks r WHERE r.id = risk_id))"
        " OR (supplier_id IS NOT NULL AND EXISTS (SELECT 1 FROM suppliers s WHERE s.id = supplier_id))"
    ),
    # Both ends must belong to the tenant, so a relationship cannot link across tenants.
    "supplier_relationships": (
        "EXISTS (SELECT 1 FROM suppliers s WHERE s.id = source_supplier_id)"
        " AND EXISTS (SELECT 1 FROM suppliers s WHERE s.id = target_supplier_id)"
    ),
    "supplier_components": (
        "EXISTS (SELECT 1 FROM suppliers s WHERE s.id = supplier_id)"
        " AND EXISTS (SELECT 1 FROM components c WHERE c.id = component_id)"
    ),
    "event_impacts": "EXISTS (SELECT 1 FROM risk_events e WHERE e.id = event_id)",
    "component_bom": (
        "EXISTS (SELECT 1 FROM components c WHERE c.id = parent_component_id)"
        " AND EXISTS (SELECT 1 FROM components c WHERE c.id = child_component_id)"
    ),
}


def _enable_rls(table: str, predicate: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_org_isolation ON {table}
        USING ({predicate})
        WITH CHECK ({predicate})
    """)


def _disable_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    for table in DIRECT_ORG_TABLES:
        _enable_rls(table, "organization_id = scirm_current_org()")
    for table, predicate in CHILD_TABLE_POLICIES.items():
        _enable_rls(table, predicate)


def downgrade() -> None:
    for table in reversed(list(CHILD_TABLE_POLICIES)):
        _disable_rls(table)
    for table in reversed(DIRECT_ORG_TABLES):
        _disable_rls(table)
