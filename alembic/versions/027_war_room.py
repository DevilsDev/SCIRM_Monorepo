"""War room: coordinating the response to a supply disruption.

- incidents: opened from a public record (its title, source and link are copied in, so the
  incident keeps them if the record is later delisted) or by hand; an owner, a status
  (open, monitoring, resolved) and a severity.
- incident_suppliers: the suppliers affected, prefilled from the record's matches.
- incident_tasks: actions assigned to members, open or done.
- incident_timeline: notes and an automatic entry for every change. Append-only for the
  application (UPDATE and DELETE are revoked in scripts/db_setup.py), like the audit log.

Every table is a tenant table with forced row-level security. Child rows also require the
incident (and, for suppliers, the supplier) to be visible in the current organization.

Revision ID: 027
Revises: 026
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWN_INCIDENT = "EXISTS (SELECT 1 FROM incidents i WHERE i.id = incident_id)"
OWN_SUPPLIER = "EXISTS (SELECT 1 FROM suppliers s WHERE s.id = supplier_id)"


def _isolate(table: str, extra: str = "") -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    check = f"organization_id = scirm_current_org(){' AND ' + extra if extra else ''}"
    op.execute(f"CREATE POLICY {table}_org_isolation ON {table} "
               f"USING (organization_id = scirm_current_org()) WITH CHECK ({check})")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE incidents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
            summary text NOT NULL DEFAULT '' CHECK (length(summary) <= 4000),
            severity text NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
            status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'monitoring', 'resolved')),
            owner_email text NULL CHECK (length(owner_email) <= 254),
            signal_id uuid NULL,
            signal jsonb NULL,
            resolution text NULL CHECK (length(resolution) <= 4000),
            opened_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX ix_incidents_status ON incidents (organization_id, status, updated_at DESC)")
    _isolate("incidents")

    op.execute("""
        CREATE TABLE incident_suppliers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
            supplier_id uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            reason text NOT NULL DEFAULT '' CHECK (length(reason) <= 300),
            added_by text NULL,
            added_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (incident_id, supplier_id)
        )
    """)
    _isolate("incident_suppliers", f"{OWN_INCIDENT} AND {OWN_SUPPLIER}")

    op.execute("""
        CREATE TABLE incident_tasks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
            title text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
            assignee_email text NULL CHECK (length(assignee_email) <= 254),
            due_date date NULL,
            status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            done_by text NULL,
            done_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX ix_incident_tasks_incident ON incident_tasks (incident_id)")
    _isolate("incident_tasks", OWN_INCIDENT)

    op.execute("""
        CREATE TABLE incident_timeline (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            -- Write order: entries written in one transaction share created_at.
            seq bigint GENERATED ALWAYS AS IDENTITY,
            organization_id uuid NOT NULL REFERENCES organizations(id),
            incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('opened', 'note', 'status', 'owner', 'severity', 'edited',
                                               'supplier_added', 'supplier_removed', 'task_added', 'task_done',
                                               'task_reopened')),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
            actor text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_incident_timeline_incident ON incident_timeline (incident_id, seq)")
    _isolate("incident_timeline", OWN_INCIDENT)


def downgrade() -> None:
    for table in ("incident_timeline", "incident_tasks", "incident_suppliers", "incidents"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
