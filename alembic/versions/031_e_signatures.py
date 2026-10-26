"""Electronic signatures with the controls of 21 CFR Part 11 (11.50, 11.70, 11.100, 11.200).

e_signatures: one row per signature, with
- the signer (a user id, never reassigned: 11.100(a)) and their printed name and email at
  the time of signing, the date and time, and the meaning (11.50(a));
- the signed record (type and id) and the SHA-256 of its exact content when signed, so the
  signature cannot be moved to another record or survive an edit unnoticed (11.70);
- how the signer re-authenticated (password, password and two-step code, or a fresh login
  at the organization's identity provider) and an optional reason.

The application role can only add and read signatures (UPDATE, DELETE and TRUNCATE are
revoked in scripts/db_setup.py), and nothing cascades to them: the record is referenced by
type and id, not by a foreign key, so deleting or editing a record never removes its
signatures. The signer references users without cascade.

Tenant table with forced row-level security.

Revision ID: 031
Revises: 030
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE e_signatures (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq bigint GENERATED ALWAYS AS IDENTITY,
            organization_id uuid NOT NULL REFERENCES organizations(id),
            signer_id uuid NOT NULL REFERENCES users(id),
            signer_name text NOT NULL CHECK (length(signer_name) BETWEEN 1 AND 255),
            signer_email text NOT NULL CHECK (length(signer_email) BETWEEN 3 AND 254),
            meaning text NOT NULL CHECK (meaning IN ('reviewed', 'approved', 'responsible')),
            reason text NULL CHECK (length(reason) <= 1000),
            record_type text NOT NULL CHECK (record_type IN ('assessment', 'incident', 'action_proposal')),
            record_id text NOT NULL CHECK (length(record_id) BETWEEN 1 AND 64),
            record_summary text NOT NULL CHECK (length(record_summary) BETWEEN 1 AND 500),
            record_hash text NOT NULL CHECK (record_hash ~ '^[0-9a-f]{64}$'),
            method text NOT NULL CHECK (method IN ('password', 'password_mfa', 'sso_reauth')),
            signed_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_e_signatures_record ON e_signatures (organization_id, record_type, record_id, seq)")
    op.execute("ALTER TABLE e_signatures ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE e_signatures FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY e_signatures_org_isolation ON e_signatures "
               "USING (organization_id = scirm_current_org()) WITH CHECK (organization_id = scirm_current_org())")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS e_signatures")
