"""Real password changes and resets.

- users.password_changed_at: refresh tokens issued before it are refused, so changing or
  resetting a password signs out other sessions (within the access token's lifetime).
  scirm_user_by_id returns it.
- password_resets: single-use reset links. Only the SHA-256 of the token is stored; it
  expires (30 minutes by default) and a new request invalidates the user's earlier ones.
  Both steps happen before the user is signed in, so they go through SECURITY DEFINER
  functions (like the login lookup): scirm_password_reset_request creates a token for an
  active account, and scirm_password_reset_consume sets the new password and uses the
  token in one statement, so a token works exactly once.

Revision ID: 022
Revises: 021
Create Date: 2026-10-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCTIONS = ("scirm_password_reset_request(text, text, timestamptz)", "scirm_password_reset_consume(text, text)")

USER_BY_ID = """
    CREATE FUNCTION scirm_user_by_id(p_id uuid)
    RETURNS TABLE (id uuid, organization_id uuid, email text, name text, roles text[],
                   is_active boolean, mfa_secret text, mfa_enabled boolean{extra})
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        SELECT u.id, u.organization_id, u.email, u.name, u.roles::text[], u.is_active,
               u.mfa_secret, u.mfa_enabled{extra_select}
        FROM users u WHERE u.id = p_id
    $$
"""


def _user_by_id(with_changed_at: bool) -> None:
    op.execute("DROP FUNCTION IF EXISTS scirm_user_by_id(uuid)")
    op.execute(USER_BY_ID.format(extra=", password_changed_at timestamptz" if with_changed_at else "",
                                 extra_select=", u.password_changed_at" if with_changed_at else ""))
    op.execute("REVOKE ALL ON FUNCTION scirm_user_by_id(uuid) FROM PUBLIC")


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN password_changed_at timestamptz NULL")
    _user_by_id(True)
    op.execute("""
        CREATE TABLE password_resets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            user_id uuid NOT NULL REFERENCES users(id),
            token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            expires_at timestamptz NOT NULL,
            used_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_password_resets_user ON password_resets (user_id)")
    # Enabled, not forced (like users): the application role sees nothing without its
    # organization, while the definer functions (the owner) work before sign-in.
    op.execute("ALTER TABLE password_resets ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY password_resets_org_isolation ON password_resets
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)
    op.execute("""
        CREATE FUNCTION scirm_password_reset_request(p_email text, p_token_hash text, p_expires timestamptz)
        RETURNS TABLE (user_id uuid, organization_id uuid, email text, name text)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE
            u users%ROWTYPE;
        BEGIN
            SELECT * INTO u FROM users WHERE lower(users.email) = lower(p_email) AND users.is_active;
            IF NOT FOUND THEN
                RETURN;
            END IF;
            -- Only the newest link works.
            UPDATE password_resets SET used_at = now() WHERE password_resets.user_id = u.id AND used_at IS NULL;
            INSERT INTO password_resets (organization_id, user_id, token_hash, expires_at)
            VALUES (u.organization_id, u.id, p_token_hash, p_expires);
            RETURN QUERY SELECT u.id, u.organization_id, u.email::text, u.name::text;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION scirm_password_reset_consume(p_token_hash text, p_password_hash text)
        RETURNS TABLE (user_id uuid, organization_id uuid, email text)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE
            r password_resets%ROWTYPE;
        BEGIN
            UPDATE password_resets SET used_at = now()
            WHERE token_hash = p_token_hash AND used_at IS NULL AND expires_at > now()
            RETURNING * INTO r;
            IF NOT FOUND THEN
                RETURN;
            END IF;
            RETURN QUERY
            UPDATE users SET hashed_password = p_password_hash, password_changed_at = now(), updated_at = now()
            WHERE users.id = r.user_id AND users.is_active
            RETURNING users.id, users.organization_id, users.email::text;
        END
        $$
    """)
    for fn in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")


def downgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.execute("DROP TABLE IF EXISTS password_resets")
    _user_by_id(False)
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at")
