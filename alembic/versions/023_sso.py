"""Single sign-on with OpenID Connect, per organization.

- sso_configs: one identity provider per organization (issuer, client id, client secret
  encrypted with secret_box and bound to "sso:<org>", enforce flag). Forced RLS: every
  read happens with the organization known (from the account at start, from the signed
  state cookie at the callback).
- users.sso_issuer / sso_subject: the identity provider's stable user id, linked at the
  first SSO sign-in and required to match afterwards (emails can be reassigned at an
  identity provider; the subject cannot). Unique per issuer.
- sso_handoffs: after the callback the browser gets a one-time code (in the URL fragment),
  not tokens. Only its hash is stored; it lasts 60 seconds, works once, and only together
  with the value the starting login page kept (binding_hash), consumed by
  scirm_sso_handoff_consume (SECURITY DEFINER: the exchange happens before sign-in).

Revision ID: 023
Revises: 022
Create Date: 2026-10-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCTIONS = ("scirm_sso_handoff_consume(text, text)",)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sso_configs (
            organization_id uuid PRIMARY KEY REFERENCES organizations(id),
            issuer text NOT NULL CHECK (length(issuer) <= 300),
            client_id text NOT NULL CHECK (length(client_id) BETWEEN 1 AND 300),
            client_secret_enc text NOT NULL CHECK (client_secret_enc LIKE 'enc:v1:%'),
            enforce boolean NOT NULL DEFAULT false,
            created_by text NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE sso_configs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sso_configs FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY sso_configs_org_isolation ON sso_configs
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)
    op.execute("ALTER TABLE users ADD COLUMN sso_issuer text NULL, ADD COLUMN sso_subject text NULL")
    op.execute("CREATE UNIQUE INDEX ux_users_sso ON users (sso_issuer, sso_subject) WHERE sso_subject IS NOT NULL")
    op.execute("""
        CREATE TABLE sso_handoffs (
            code_hash text PRIMARY KEY CHECK (code_hash ~ '^[0-9a-f]{64}$'),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            user_id uuid NOT NULL REFERENCES users(id),
            -- SHA-256 of a random value kept by the login page that started the sign-in: the
            -- code only works in that browser (no login CSRF with a captured code).
            binding_hash text NOT NULL CHECK (binding_hash ~ '^[0-9a-f]{64}$'),
            expires_at timestamptz NOT NULL,
            used_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    # Enabled, not forced (like users): inserts happen with the organization set; the
    # consume function (the owner) works before sign-in, also with a non-superuser owner.
    op.execute("ALTER TABLE sso_handoffs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY sso_handoffs_org_isolation ON sso_handoffs
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)
    op.execute("""
        CREATE FUNCTION scirm_sso_handoff_consume(p_code_hash text, p_binding_hash text)
        RETURNS TABLE (user_id uuid, organization_id uuid)
        LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
            -- A wrong binding leaves the code unused, so it cannot be burnt by someone else.
            UPDATE sso_handoffs SET used_at = now()
            WHERE code_hash = p_code_hash AND binding_hash = p_binding_hash
              AND used_at IS NULL AND expires_at > now()
            RETURNING sso_handoffs.user_id, sso_handoffs.organization_id
        $$
    """)
    for fn in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")


def downgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.execute("DROP TABLE IF EXISTS sso_handoffs")
    op.execute("DROP INDEX IF EXISTS ux_users_sso")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS sso_subject, DROP COLUMN IF EXISTS sso_issuer")
    op.execute("DROP TABLE IF EXISTS sso_configs")
