"""User feedback on matched public records and Evidence Engine answers.

This feeds the Phase 1 gate metrics: the share of alerts confirmed useful, the
wrong-supplier rate, and citations reported as wrong. Each user has one rating per
item and can change it. Tenant-scoped with forced row-level security, like the other
tenant tables. No question text is stored: feedback on an answer records which
citations were shown, not what was asked.

Revision ID: 016
Revises: 015
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE feedback (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            user_id text NOT NULL,
            target_type text NOT NULL CHECK (target_type IN ('signal_match', 'answer', 'citation')),
            target_id text NOT NULL,
            supplier_id text NULL,
            verdict text NOT NULL CHECK (verdict IN ('useful', 'not_useful', 'wrong_supplier', 'incorrect')),
            reason text NULL CHECK (length(reason) <= 500),
            context jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT feedback_one_per_user UNIQUE (organization_id, user_id, target_type, target_id)
        )
    """)
    op.execute("CREATE INDEX ix_feedback_org_created ON feedback (organization_id, created_at DESC)")
    op.execute("ALTER TABLE feedback ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE feedback FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY feedback_org_isolation ON feedback
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedback")
