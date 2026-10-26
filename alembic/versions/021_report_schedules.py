"""Scheduled reports: a supplier risk digest emailed to members on a schedule.

The digest lists the organization's new matches in the period: public records naming its
suppliers and disaster exposures, as recorded by the webhook detector in webhook_events
(migration 020), whether or not the organization uses webhooks.

next_run_at drives the runner: a coordinator claims due schedules with FOR UPDATE SKIP
LOCKED and moves next_run_at forward before sending, so two replicas never send the same
run. Times are UTC. Recipients are checked against the organization's members when saved
and again when sent. Tenant table with forced row-level security.

Revision ID: 021
Revises: 020
Create Date: 2026-10-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE report_schedules (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
            kind text NOT NULL DEFAULT 'supplier_digest' CHECK (kind IN ('supplier_digest')),
            frequency text NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly')),
            weekday smallint NULL CHECK (weekday BETWEEN 0 AND 6),
            hour_utc smallint NOT NULL CHECK (hour_utc BETWEEN 0 AND 23),
            recipients text[] NOT NULL CHECK (cardinality(recipients) BETWEEN 1 AND 20),
            skip_empty boolean NOT NULL DEFAULT false,
            active boolean NOT NULL DEFAULT true,
            next_run_at timestamptz NOT NULL,
            last_run_at timestamptz NULL,
            last_status jsonb NULL,
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT report_schedules_weekly_has_day CHECK (frequency <> 'weekly' OR weekday IS NOT NULL)
        )
    """)
    op.execute("CREATE INDEX ix_report_schedules_due ON report_schedules (organization_id, active, next_run_at)")
    op.execute("ALTER TABLE report_schedules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE report_schedules FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY report_schedules_org_isolation ON report_schedules
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS report_schedules")
