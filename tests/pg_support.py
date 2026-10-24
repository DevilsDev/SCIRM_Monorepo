"""
Helpers for tests that run against a real PostgreSQL server.

Set TEST_POSTGRES_URL to a superuser URL (any database, e.g. .../postgres).
Each caller gets a freshly created database, migrated to head, with a restricted
application role (NOSUPERUSER, NOBYPASSRLS, not the owner) so row-level
security really applies — a superuser connection would silently bypass it.
"""

import asyncio
import importlib.util
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
APP_ROLE = "scirm_app_test"
APP_PASSWORD = "test-app-password"


def postgres_url() -> str:
    return os.environ.get("TEST_POSTGRES_URL", "")


def _with(url: str, *, user: str = None, password: str = None, database: str = None) -> str:
    parts = urlsplit(url)
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    u = user if user is not None else (parts.username or "")
    pw = password if password is not None else (parts.password or "")
    auth = f"{u}:{pw}@" if pw else f"{u}@"
    path = f"/{database}" if database is not None else parts.path
    return urlunsplit((parts.scheme, auth + host, path, parts.query, parts.fragment))


def _db_setup():
    spec = importlib.util.spec_from_file_location("scirm_db_setup", ROOT / "scripts" / "db_setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh_database(name: str, seed_demo: bool = True) -> dict:
    """Create (or recreate) database `name`; return owner and app-role URLs."""
    import psycopg2

    admin = postgres_url().replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = psycopg2.connect(admin)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
    cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
    cur.execute(f'CREATE DATABASE "{name}"')
    conn.close()

    owner_url = _with(admin, database=name)
    setup = _db_setup()
    setup.run_migrations(owner_url)
    setup.ensure_app_role(owner_url, APP_ROLE, APP_PASSWORD)
    if seed_demo:
        asyncio.run(setup.seed_demo(owner_url))
    return {"owner": owner_url, "app": _with(owner_url, user=APP_ROLE, password=APP_PASSWORD)}
