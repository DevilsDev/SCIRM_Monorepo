"""Supplier ownership from the Global LEI Index (GLEIF).

supplier_ownership: one row per supplier that a person has linked to a Legal Entity
Identifier. It keeps who confirmed the link and when, and the last GLEIF answer for the
entity and its direct and ultimate parents (snapshot, refreshed_at), so shared owners can
be shown across suppliers without calling GLEIF for each one. A supplier without a row
has no confirmed LEI: its ownership is unknown, not independent.

Removing a link deletes the row; the link and its removal stay in the audit log.

Revision ID: 033
Revises: 032
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE supplier_ownership (
            supplier_id uuid PRIMARY KEY REFERENCES suppliers(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            lei varchar(20) NOT NULL CHECK (lei ~ '^[A-Z0-9]{18}[0-9]{2}$'),
            snapshot jsonb NOT NULL,
            confirmed_by text NOT NULL,
            confirmed_at timestamptz NOT NULL DEFAULT now(),
            refreshed_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_supplier_ownership_org ON supplier_ownership (organization_id)")
    op.execute("ALTER TABLE supplier_ownership ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE supplier_ownership FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY supplier_ownership_org_isolation ON supplier_ownership "
               "USING (organization_id = scirm_current_org()) "
               "WITH CHECK (organization_id = scirm_current_org() "
               "AND EXISTS (SELECT 1 FROM suppliers s WHERE s.id = supplier_id))")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supplier_ownership")
