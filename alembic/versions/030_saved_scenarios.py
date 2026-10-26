"""Scenario studio: saved scenario definitions (which suppliers are out, for how long, and the
planner's assumptions). Results are not stored: they are computed from current spend and
assessment answers each time a scenario is run (libs/scenarios/engine.py).

Tenant table with forced row-level security.

Revision ID: 030
Revises: 029
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE saved_scenarios (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
            definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE saved_scenarios ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE saved_scenarios FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY saved_scenarios_org_isolation ON saved_scenarios "
               "USING (organization_id = scirm_current_org()) WITH CHECK (organization_id = scirm_current_org())")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_scenarios")
