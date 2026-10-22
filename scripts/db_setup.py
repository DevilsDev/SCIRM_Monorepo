"""
Prepare a SCIRM database: run migrations as the owner, create the application
role the services connect as, and optionally seed the demo tenants.

The application role is deliberately NOSUPERUSER, NOBYPASSRLS and not the table
owner, so PostgreSQL row-level security applies to every query it makes. It may
read and append the audit log but never update or delete it.

Usage:
  python scripts/db_setup.py --owner-url postgresql://scirm:...@host/db \\
      --app-role scirm_app --app-password '...' [--seed-demo]
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def run_migrations(owner_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_URL"] = owner_url  # alembic/env.py reads it
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def ensure_app_role(owner_url: str, role: str, password: str) -> None:
    import psycopg2
    from psycopg2 import sql

    if not _ROLE_RE.match(role):
        raise ValueError(f"invalid role name {role!r}")
    conn = psycopg2.connect(_sync_url(owner_url))
    conn.autocommit = True
    cur = conn.cursor()
    ident = sql.Identifier(role)
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
    if cur.fetchone():
        cur.execute(sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s").format(ident), (password,))
    else:
        cur.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s").format(ident), (password,))
    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(ident))
    cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(ident))
    cur.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(ident))
    # The audit log is append-only for the application (a trigger also enforces this).
    cur.execute(sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {}").format(ident))
    # Migrations are not for the application role.
    cur.execute(sql.SQL("REVOKE ALL ON alembic_version FROM {}").format(ident))
    # The only lookups allowed before a tenant is known (login, refresh, invitations: migration
    # 015; API keys: migration 019).
    for fn in ("scirm_login_lookup(text)", "scirm_user_by_id(uuid)", "scirm_invitation_lookup(text)",
               "scirm_accept_invitation(text, text, text)", "scirm_api_key_lookup(text)"):
        cur.execute(sql.SQL("GRANT EXECUTE ON FUNCTION " + fn + " TO {}").format(ident))
    conn.close()


async def seed_demo(url: str) -> None:
    from libs.common.store import PostgresStore

    store = PostgresStore(url)
    try:
        await store.seed_demo()
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--owner-url", default=os.getenv("DATABASE_OWNER_URL"), required=os.getenv("DATABASE_OWNER_URL") is None)
    parser.add_argument("--app-role", default=os.getenv("DATABASE_APP_ROLE", "scirm_app"))
    parser.add_argument("--app-password", default=os.getenv("DATABASE_APP_PASSWORD"))
    parser.add_argument("--seed-demo", action="store_true", help="create the demo tenants and suppliers (development only)")
    args = parser.parse_args()
    if not args.app_password:
        parser.error("--app-password (or DATABASE_APP_PASSWORD) is required")

    run_migrations(args.owner_url)
    ensure_app_role(args.owner_url, args.app_role, args.app_password)
    if args.seed_demo:
        asyncio.run(seed_demo(args.owner_url))
    print(f"database ready; application role {args.app_role!r} configured")


if __name__ == "__main__":
    main()
