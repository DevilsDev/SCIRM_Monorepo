"""Regulatory watch: each organization's watchlist of active substances and products.

FDA and EMA records (recalls, shortages, warning letters, import alerts, EMA shortages,
safety communications and referrals) that name a watched term are shown on the
Regulatory watch screen, sent as watchlist.matched webhooks and listed in the digest.
EMA names medicines and substances, not manufacturers, which is why this is a list of
terms rather than a match on supplier names.

Tenant table with forced row-level security. A term is unique per organization,
regardless of case. The webhook event checks (migration 020) gain watchlist.matched.

Revision ID: 026
Revises: 025
Create Date: 2026-10-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _event_checks(types: str) -> None:
    op.execute("ALTER TABLE webhooks DROP CONSTRAINT webhooks_events_check")
    op.execute(f"ALTER TABLE webhooks ADD CONSTRAINT webhooks_events_check "
               f"CHECK (events <@ ARRAY[{types}]::text[] AND cardinality(events) > 0)")
    op.execute("ALTER TABLE webhook_events DROP CONSTRAINT webhook_events_type_check")
    op.execute(f"ALTER TABLE webhook_events ADD CONSTRAINT webhook_events_type_check "
               f"CHECK (type IN ({types}, 'ping'))")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watchlist_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            kind text NOT NULL CHECK (kind IN ('substance', 'product')),
            term text NOT NULL CHECK (length(term) BETWEEN 3 AND 100),
            note text NOT NULL DEFAULT '' CHECK (length(note) <= 300),
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_watchlist_items_term ON watchlist_items (organization_id, lower(term))")
    op.execute("ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE watchlist_items FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY watchlist_items_org_isolation ON watchlist_items
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)
    _event_checks("'record.matched', 'exposure.detected', 'watchlist.matched'")


def downgrade() -> None:
    op.execute("DELETE FROM webhook_deliveries WHERE event_id IN "
               "(SELECT id FROM webhook_events WHERE type = 'watchlist.matched')")
    op.execute("DELETE FROM webhook_events WHERE type = 'watchlist.matched'")
    op.execute("UPDATE webhooks SET events = array_remove(events, 'watchlist.matched')")
    op.execute("UPDATE webhooks SET events = ARRAY['record.matched'] WHERE cardinality(events) = 0")
    _event_checks("'record.matched', 'exposure.detected'")
    op.execute("DROP TABLE IF EXISTS watchlist_items")
