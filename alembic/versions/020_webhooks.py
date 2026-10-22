"""Webhooks: events when new public records match a tenant's suppliers.

- webhooks: an organization's endpoints. The signing secret is stored encrypted
  (libs/common/secret_box.py, bound to "webhook:<org>:<id>") and shown once.
- webhook_events: one row per event. UNIQUE (organization_id, dedupe_key) makes detection
  idempotent: a second detector run, or a second replica, inserts nothing new, and
  deliveries are only created for rows actually inserted.
- webhook_deliveries: one row per event and endpoint, retried with backoff. A worker
  claims due rows with FOR UPDATE SKIP LOCKED and a short lease (next_attempt_at).
- notification_state: per organization, the first_seen_at of public records already
  considered. Set on the first run without emitting anything, so turning webhooks on
  does not replay the archive.

All four are tenant tables with forced row-level security.

Revision ID: 020
Revises: 019
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("webhook_deliveries", "webhook_events", "webhooks", "notification_state")


def _tenant(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_org_isolation ON {table}
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE notification_state (
            organization_id uuid PRIMARY KEY REFERENCES organizations(id),
            watermark timestamptz NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE webhooks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            url text NOT NULL CHECK (length(url) <= 500),
            description text NULL CHECK (length(description) <= 200),
            events text[] NOT NULL CHECK (events <@ ARRAY['record.matched', 'exposure.detected']::text[]
                                          AND cardinality(events) > 0),
            secret_enc text NOT NULL CHECK (secret_enc LIKE 'enc:v1:%'),
            active boolean NOT NULL DEFAULT true,
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_delivery jsonb NULL
        )
    """)
    op.execute("CREATE INDEX ix_webhooks_org ON webhooks (organization_id)")
    op.execute("""
        CREATE TABLE webhook_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            type text NOT NULL CHECK (type IN ('record.matched', 'exposure.detected', 'ping')),
            dedupe_key text NOT NULL CHECK (length(dedupe_key) <= 300),
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT webhook_events_once UNIQUE (organization_id, dedupe_key)
        )
    """)
    op.execute("""
        CREATE TABLE webhook_deliveries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            webhook_id uuid NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
            event_id uuid NOT NULL REFERENCES webhook_events(id),
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed')),
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            last_status_code integer NULL,
            last_error text NULL CHECK (length(last_error) <= 300),
            delivered_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT webhook_deliveries_once UNIQUE (webhook_id, event_id)
        )
    """)
    op.execute("CREATE INDEX ix_webhook_deliveries_due ON webhook_deliveries (organization_id, status, next_attempt_at)")
    op.execute("CREATE INDEX ix_webhook_deliveries_webhook ON webhook_deliveries (webhook_id, created_at DESC)")
    for table in TABLES:
        _tenant(table)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
