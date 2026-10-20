"""
Database-level guarantees, checked with raw SQL against real PostgreSQL.
Skipped unless TEST_POSTGRES_URL (a superuser URL) is set.

Queries run as the restricted application role: a superuser would bypass
row-level security and make every isolation test pass falsely.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
import pg_support  # noqa: E402

pytestmark = pytest.mark.skipif(not pg_support.postgres_url(), reason="TEST_POSTGRES_URL not set")

psycopg2 = pytest.importorskip("psycopg2")


@pytest.fixture(scope="module")
def db():
    urls = pg_support.fresh_database("scirm_test_db", seed_demo=False)
    owner = psycopg2.connect(urls["owner"])
    owner.autocommit = True
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    with owner.cursor() as cur:
        cur.execute("INSERT INTO organizations (id, name, industry) VALUES (%s, 'A', 'pharma'), (%s, 'B', 'pharma')",
                    (org_a, org_b))
    app = psycopg2.connect(urls["app"])
    yield {"owner": owner, "app": app, "a": org_a, "b": org_b, "urls": urls}
    app.close()
    owner.close()


def as_org(conn, org, sql, args=()):
    """Run one statement as the app role inside a transaction scoped to `org`."""
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT set_config('app.current_org_id', %s, true)", (org,))
            cur.execute(sql, args)
            rows = cur.fetchall() if cur.description else cur.rowcount
            conn.commit()
            return rows
        except Exception as exc:
            conn.rollback()
            return exc


def test_app_role_is_restricted(db):
    with db["owner"].cursor() as cur:
        cur.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", (pg_support.APP_ROLE,))
        assert cur.fetchone() == (False, False)


class TestRowLevelSecurity:
    def test_insert_into_own_org(self, db):
        assert as_org(db["app"], db["a"], "INSERT INTO suppliers (organization_id, supplier_code, name) VALUES (%s, 'A1', 'Sup A')",
                      (db["a"],)) == 1

    def test_cannot_write_another_orgs_row(self, db):
        result = as_org(db["app"], db["a"], "INSERT INTO suppliers (organization_id, supplier_code, name) VALUES (%s, 'B1', 'Sup B')",
                        (db["b"],))
        assert isinstance(result, psycopg2.errors.InsufficientPrivilege)

    def test_other_org_sees_nothing(self, db):
        assert as_org(db["app"], db["b"], "SELECT name FROM suppliers") == []

    def test_no_org_set_sees_nothing(self, db):
        assert as_org(db["app"], "", "SELECT name FROM suppliers") == []

    def test_cross_tenant_update_and_delete_affect_nothing(self, db):
        assert as_org(db["app"], db["b"], "UPDATE suppliers SET name = 'pwned'") == 0
        assert as_org(db["app"], db["b"], "DELETE FROM suppliers") == 0
        assert as_org(db["app"], db["a"], "SELECT name FROM suppliers") == [("Sup A",)]

    def test_child_rows_cannot_hang_off_another_orgs_parent(self, db):
        [(assessment,)] = as_org(db["app"], db["a"],
                                 "INSERT INTO risk_assessments (task_id, organization_id) VALUES ('t-a', %s) RETURNING id", (db["a"],))
        result = as_org(db["app"], db["b"],
                        "INSERT INTO recommendations (assessment_id, title, description) VALUES (%s, 'r', 'd')", (assessment,))
        assert isinstance(result, psycopg2.errors.InsufficientPrivilege)

    def test_risks_are_scoped_by_their_own_org(self, db):
        insert = ("INSERT INTO risks (organization_id, title, description, severity, probability, impact_score) "
                  "VALUES (%s, 'manual', 'd', 'high', 0.5, 5)")
        assert as_org(db["app"], db["a"], insert, (db["a"],)) == 1
        assert isinstance(as_org(db["app"], db["a"], insert, (db["b"],)), psycopg2.errors.InsufficientPrivilege)
        assert as_org(db["app"], db["b"], "SELECT count(*) FROM risks") == [(0,)]


class TestAuditLog:
    def _insert(self, db, org):
        return as_org(db["app"], org, "INSERT INTO audit_logs (organization_id, action, resource_type) VALUES (%s, 'POST /x', 'x')",
                      (org,))

    def test_audit_rows_are_tenant_scoped(self, db):
        assert self._insert(db, db["a"]) == 1
        assert as_org(db["app"], db["b"], "SELECT count(*) FROM audit_logs") == [(0,)]
        assert as_org(db["app"], db["a"], "SELECT count(*) FROM audit_logs")[0][0] >= 1

    def test_app_role_cannot_update_or_delete_audit_rows(self, db):
        self._insert(db, db["a"])
        assert isinstance(as_org(db["app"], db["a"], "UPDATE audit_logs SET action = 'tampered'"),
                          psycopg2.errors.InsufficientPrivilege)
        assert isinstance(as_org(db["app"], db["a"], "DELETE FROM audit_logs"), psycopg2.errors.InsufficientPrivilege)

    def test_even_the_owner_cannot_rewrite_history(self, db):
        with db["owner"].cursor() as cur:
            for sql in ("UPDATE audit_logs SET action = 'tampered'", "DELETE FROM audit_logs", "TRUNCATE audit_logs"):
                with pytest.raises(psycopg2.Error, match="append-only"):
                    cur.execute(sql)


class TestPublicSignals:
    """Public records: readable and writable by the app role, no tenant scoping."""

    def _run(self, db, coro_factory):
        import asyncio
        sys.path.insert(0, str(ROOT))
        os.environ["DB_POOL"] = "null"
        from libs.common.store import PostgresStore

        async def go():
            store = PostgresStore(db["urls"]["app"])
            try:
                return await coro_factory(store)
            finally:
                await store.close()
        return asyncio.run(go())

    def test_upsert_is_idempotent_and_filters_by_latest_activity(self, db):
        signal = {"source": "fda_shortages", "external_id": "db-x", "signal_type": "shortage", "title": "Shortage: X",
                  "summary": "", "severity": "high", "entity_names": ["Hospira, Inc."], "entity_keys": ["hospira"],
                  "country_codes": [], "published_at": "2012-02-22", "updated_at": "2026-10-08", "raw": {}}

        async def steps(store):
            first = await store.upsert_signals([signal])
            again = await store.upsert_signals([{**signal, "severity": "medium"}])
            recent, _ = await store.list_signals(since="2026-09-20")
            candidates = await store.signal_candidates(["hospira"], [], since="2026-09-20")
            return first, again, recent, candidates

        first, again, recent, candidates = self._run(db, steps)
        assert (first, again) == (1, 0)
        assert [s["external_id"] for s in recent] == ["db-x"] and recent[0]["severity"] == "medium"
        assert [s["external_id"] for s in candidates] == ["db-x"]

    def test_retire_unseen_delists_and_upsert_relists(self, db):
        base = {"source": "fda_import_alerts", "signal_type": "import_alert", "title": "IA", "summary": "",
                "severity": "high", "entity_names": ["Acme"], "entity_keys": ["acme"], "country_codes": ["IN"],
                "published_at": "2024-01-01", "updated_at": "2026-10-20", "raw": {}}
        a, b = {**base, "external_id": "ia-a"}, {**base, "external_id": "ia-b"}

        async def steps(store):
            await store.upsert_signals([a, b])
            retired = await store.retire_unseen("fda_import_alerts", ["ia-a"])
            after_retire = [s["external_id"] for s in await store.signal_candidates(["acme"], [], limit=10)]
            again = await store.retire_unseen("fda_import_alerts", ["ia-a"])
            await store.upsert_signals([b])  # listed again
            after_relist = sorted(s["external_id"] for s in await store.signal_candidates(["acme"], [], limit=10))
            return retired, after_retire, again, after_relist

        retired, after_retire, again, after_relist = self._run(db, steps)
        assert (retired, after_retire, again) == (1, ["ia-a"], 0)
        assert after_relist == ["ia-a", "ia-b"]

    def test_public_signals_are_visible_to_every_tenant(self, db):
        rows_a = as_org(db["app"], db["a"], "SELECT count(*) FROM public_signals")
        rows_b = as_org(db["app"], db["b"], "SELECT count(*) FROM public_signals")
        assert rows_a == rows_b and rows_a[0][0] >= 1


def test_migrations_downgrade_and_reapply(db):
    """The whole chain must round-trip, so a bad release can be rolled back."""
    env = dict(os.environ, DATABASE_URL=db["urls"]["owner"])
    alembic = [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini")]
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run(alembic + args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stderr[-2000:]
