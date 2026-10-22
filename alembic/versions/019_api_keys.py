"""API keys for the read-only public API.

A key belongs to its organization (created_by records who made it). Only the SHA-256 of
the key is stored: keys are 32 random bytes, so a slow hash adds nothing, and the full key
is shown once at creation. The prefix ("scirm_" plus 8 characters) identifies a key in
lists and in the audit log.

Row-level security is enabled but not forced, as on users: the application role is not
the owner, so it only sees its organization's keys, while scirm_api_key_lookup (SECURITY
DEFINER, owner) can find a key before its organization is known, also when the owner is
not a superuser (managed PostgreSQL).

Revision ID: 019
Revises: 018
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCTIONS = ("scirm_api_key_lookup(text)",)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE api_keys (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
            prefix text NOT NULL CHECK (prefix ~ '^scirm_[A-Za-z0-9]{8}$'),
            key_hash text NOT NULL UNIQUE CHECK (key_hash ~ '^[0-9a-f]{64}$'),
            scopes text[] NOT NULL DEFAULT '{read}' CHECK (scopes <@ ARRAY['read']::text[]),
            created_by text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NULL,
            last_used_at timestamptz NULL,
            revoked_at timestamptz NULL
        )
    """)
    op.execute("CREATE INDEX ix_api_keys_org ON api_keys (organization_id, created_at DESC)")
    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY api_keys_org_isolation ON api_keys
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)
    op.execute("""
        CREATE FUNCTION scirm_api_key_lookup(p_key_hash text)
        RETURNS TABLE (id uuid, organization_id uuid, name text, prefix text, scopes text[], live boolean)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            -- Revoked and expired keys are returned too (live = false), so a refused
            -- request is recorded in the key's organization.
            SELECT k.id, k.organization_id, k.name, k.prefix, k.scopes,
                   k.revoked_at IS NULL AND (k.expires_at IS NULL OR k.expires_at > now())
            FROM api_keys k
            WHERE k.key_hash = p_key_hash
        $$
    """)
    for fn in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")


def downgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.execute("DROP TABLE IF EXISTS api_keys")
