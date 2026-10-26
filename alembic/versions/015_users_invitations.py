"""Persistent users and invitations, so customers can be onboarded and add teammates.

Tenant isolation:
- users and invitations get row-level security by organization. RLS is ENABLED but not
  FORCED: the application connects as scirm_app, which is not the table owner, so the
  policies apply to every query it makes. FORCE would also apply them to the owner, and
  the SECURITY DEFINER functions below run as the owner. On managed PostgreSQL the owner
  is usually not a superuser, so with FORCE those functions would see no rows and login
  would break. tests/db checks this with a non-superuser owner.
- Login, refresh, and invitation lookup/acceptance must find a row before any
  organization is known. They go through four narrow SECURITY DEFINER functions with a
  fixed search_path, returning only the columns needed. EXECUTE is revoked from PUBLIC and
  granted to the application role by scripts/db_setup.py.

Emails are compared case-insensitively. Invitation tokens are stored only as SHA-256
hashes. Acceptance is a single atomic step that works once, before expiry and only if
not revoked.

Revision ID: 015
Revises: 014
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCTIONS = ("scirm_login_lookup(text)", "scirm_user_by_id(uuid)", "scirm_invitation_lookup(text)",
             "scirm_accept_invitation(text, text, text)")


def upgrade() -> None:
    # --- users: case-insensitive email, tenant RLS ---
    op.execute("UPDATE users SET email = lower(email)")
    op.execute("CREATE UNIQUE INDEX ux_users_email_lower ON users (lower(email))")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY users_org_isolation ON users
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)

    # --- invitations ---
    op.execute("""
        CREATE TABLE invitations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            email text NOT NULL,
            roles text[] NOT NULL,
            token_hash text NOT NULL UNIQUE,
            invited_by uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            accepted_at timestamptz NULL,
            accepted_user_id uuid NULL,
            revoked_at timestamptz NULL,
            CONSTRAINT invitations_email_lower CHECK (email = lower(email))
        )
    """)
    op.execute("CREATE INDEX ix_invitations_org ON invitations (organization_id, created_at DESC)")
    op.execute("ALTER TABLE invitations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY invitations_org_isolation ON invitations
        USING (organization_id = scirm_current_org())
        WITH CHECK (organization_id = scirm_current_org())
    """)

    # --- pre-organization lookups ---
    op.execute("""
        CREATE FUNCTION scirm_login_lookup(p_email text)
        RETURNS TABLE (id uuid, organization_id uuid, email text, name text, hashed_password text,
                       roles text[], is_active boolean, mfa_secret text, mfa_enabled boolean)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT u.id, u.organization_id, u.email, u.name, u.hashed_password, u.roles::text[],
                   u.is_active, u.mfa_secret, u.mfa_enabled
            FROM users u WHERE lower(u.email) = lower(p_email)
        $$
    """)
    op.execute("""
        CREATE FUNCTION scirm_user_by_id(p_id uuid)
        RETURNS TABLE (id uuid, organization_id uuid, email text, name text, roles text[],
                       is_active boolean, mfa_secret text, mfa_enabled boolean)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT u.id, u.organization_id, u.email, u.name, u.roles::text[], u.is_active,
                   u.mfa_secret, u.mfa_enabled
            FROM users u WHERE u.id = p_id
        $$
    """)
    op.execute("""
        CREATE FUNCTION scirm_invitation_lookup(p_token_hash text)
        RETURNS TABLE (id uuid, organization_id uuid, organization_name text, email text, roles text[],
                       expires_at timestamptz)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT i.id, i.organization_id, o.name::text, i.email, i.roles, i.expires_at
            FROM invitations i JOIN organizations o ON o.id = i.organization_id
            WHERE i.token_hash = p_token_hash AND i.accepted_at IS NULL AND i.revoked_at IS NULL
              AND i.expires_at > now()
        $$
    """)
    # Atomic: the invitation is claimed and the user created in one statement's transaction,
    # so a token cannot be used twice. The email comes from the invitation, never the caller.
    op.execute("""
        CREATE FUNCTION scirm_accept_invitation(p_token_hash text, p_name text, p_hashed_password text)
        RETURNS TABLE (user_id uuid, organization_id uuid, email text, roles text[])
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE
            inv invitations%ROWTYPE;
            new_id uuid;
        BEGIN
            UPDATE invitations i SET accepted_at = now()
            WHERE i.token_hash = p_token_hash AND i.accepted_at IS NULL AND i.revoked_at IS NULL
              AND i.expires_at > now()
            RETURNING i.* INTO inv;
            IF NOT FOUND THEN
                RETURN;
            END IF;
            IF EXISTS (SELECT 1 FROM users u WHERE lower(u.email) = inv.email) THEN
                RAISE EXCEPTION 'email already registered' USING ERRCODE = 'unique_violation';
            END IF;
            INSERT INTO users (email, name, hashed_password, roles, organization_id, is_active)
            VALUES (inv.email, p_name, p_hashed_password, inv.roles, inv.organization_id, true)
            RETURNING users.id INTO new_id;
            UPDATE invitations SET accepted_user_id = new_id WHERE invitations.id = inv.id;
            RETURN QUERY SELECT new_id, inv.organization_id, inv.email, inv.roles;
        END
        $$
    """)
    for fn in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")


def downgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.execute("DROP TABLE IF EXISTS invitations")
    op.execute("DROP POLICY IF EXISTS users_org_isolation ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ux_users_email_lower")
