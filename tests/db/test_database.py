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


class TestAccounts:
    """Users and invitations (migration 015): tenant RLS, and the pre-tenant lookup functions."""

    def _user(self, db, org, email):
        with db["owner"].cursor() as cur:
            cur.execute("INSERT INTO users (email, name, hashed_password, roles, organization_id) "
                        "VALUES (%s, 'U', '$2b$fake', ARRAY['analyst'], %s) RETURNING id", (email, org))
            return str(cur.fetchone()[0])

    def test_users_are_tenant_scoped(self, db):
        self._user(db, db["a"], "rls-a@example.com")
        assert as_org(db["app"], db["b"], "SELECT email FROM users WHERE email = 'rls-a@example.com'") == []
        assert as_org(db["app"], db["a"], "SELECT email FROM users WHERE email = 'rls-a@example.com'") ==             [("rls-a@example.com",)]
        assert as_org(db["app"], db["b"], "UPDATE users SET name = 'x' WHERE email = 'rls-a@example.com'") == 0

    def test_emails_are_unique_regardless_of_case(self, db):
        self._user(db, db["a"], "case@example.com")
        with db["owner"].cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("INSERT INTO users (email, name, hashed_password, organization_id) "
                        "VALUES ('CASE@example.com', 'U', 'h', %s)", (db["b"],))

    def test_login_lookup_works_before_any_tenant_is_known(self, db):
        self._user(db, db["a"], "lookup@example.com")
        rows = as_org(db["app"], "", "SELECT email, organization_id::text FROM scirm_login_lookup('LOOKUP@example.com')")
        assert rows == [("lookup@example.com", db["a"])]

    def test_lookup_functions_are_not_public(self, db):
        with db["owner"].cursor() as cur:
            cur.execute("DROP ROLE IF EXISTS scirm_outsider")
            cur.execute("CREATE ROLE scirm_outsider LOGIN PASSWORD 'outsider'")
            cur.execute("GRANT USAGE ON SCHEMA public TO scirm_outsider")
        url = pg_support._with(db["urls"]["owner"], user="scirm_outsider", password="outsider")
        outsider = psycopg2.connect(url)
        try:
            result = as_org(outsider, "", "SELECT * FROM scirm_login_lookup('lookup@example.com')")
            assert isinstance(result, psycopg2.errors.InsufficientPrivilege)
        finally:
            outsider.close()

    def test_lookups_work_when_the_owner_is_not_a_superuser(self, db):
        """Managed PostgreSQL: the table owner is an ordinary role. RLS is enabled but not
        forced on users, so the SECURITY DEFINER lookups (running as the owner) still see rows."""
        self._user(db, db["a"], "managed@example.com")
        with db["owner"].cursor() as cur:
            cur.execute("DROP ROLE IF EXISTS scirm_plain_owner")
            cur.execute("CREATE ROLE scirm_plain_owner NOSUPERUSER NOBYPASSRLS")
            for obj in ("TABLE users", "TABLE invitations", "TABLE organizations", "TABLE api_keys", "TABLE password_resets",
                        "TABLE sso_handoffs"):
                cur.execute(f"ALTER {obj} OWNER TO scirm_plain_owner")
            for fn in ("scirm_login_lookup(text)", "scirm_user_by_id(uuid)", "scirm_invitation_lookup(text)",
                       "scirm_accept_invitation(text, text, text)", "scirm_api_key_lookup(text)",
                       "scirm_password_reset_request(text, text, timestamptz)", "scirm_password_reset_consume(text, text)",
                       "scirm_sso_handoff_consume(text)"):
                cur.execute(f"ALTER FUNCTION {fn} OWNER TO scirm_plain_owner")
        try:
            rows = as_org(db["app"], "", "SELECT email FROM scirm_login_lookup('managed@example.com')")
            assert rows == [("managed@example.com",)]
            as_org(db["app"], db["a"], "INSERT INTO api_keys (organization_id, name, prefix, key_hash) "
                   "VALUES (%s, 'm', 'scirm_ABCDEFGH', %s)", (db["a"], "9" * 64))
            assert as_org(db["app"], "", "SELECT name FROM scirm_api_key_lookup(%s)", ("9" * 64,)) == [("m",)]
            reset = "SELECT email FROM scirm_password_reset_request('managed@example.com', %s, now() + interval '5 minutes')"
            assert as_org(db["app"], "", reset, ("8" * 64,)) == [("managed@example.com",)]
            consume = "SELECT email FROM scirm_password_reset_consume(%s, 'new-hash')"
            assert as_org(db["app"], "", consume, ("8" * 64,)) == [("managed@example.com",)]
            assert as_org(db["app"], "", consume, ("8" * 64,)) == []  # once
            uid = as_org(db["app"], db["a"], "SELECT id::text FROM users WHERE email = %s", ("managed@example.com",))[0][0]
            as_org(db["app"], db["a"], "INSERT INTO sso_handoffs (code_hash, organization_id, user_id, expires_at) "
                   "VALUES (%s, %s, %s, now() + interval '1 minute')", ("7" * 64, db["a"], uid))
            handoff = "SELECT user_id::text FROM scirm_sso_handoff_consume(%s)"
            assert as_org(db["app"], "", handoff, ("7" * 64,)) == [(uid,)]
            assert as_org(db["app"], "", handoff, ("7" * 64,)) == []  # once
        finally:
            with db["owner"].cursor() as cur:
                cur.execute("SELECT current_user")
                me = cur.fetchone()[0]
                for obj in ("TABLE users", "TABLE invitations", "TABLE organizations", "TABLE api_keys", "TABLE password_resets",
                        "TABLE sso_handoffs"):
                    cur.execute(f"ALTER {obj} OWNER TO {me}")
                for fn in ("scirm_login_lookup(text)", "scirm_user_by_id(uuid)", "scirm_invitation_lookup(text)",
                           "scirm_accept_invitation(text, text, text)", "scirm_api_key_lookup(text)",
                       "scirm_password_reset_request(text, text, timestamptz)", "scirm_password_reset_consume(text, text)",
                       "scirm_sso_handoff_consume(text)"):
                    cur.execute(f"ALTER FUNCTION {fn} OWNER TO {me}")

    def test_an_invitation_can_be_accepted_only_once_even_concurrently(self, db):
        import hashlib
        import threading
        digest = hashlib.sha256(b"concurrent-token").hexdigest()
        with db["owner"].cursor() as cur:
            cur.execute("INSERT INTO invitations (organization_id, email, roles, token_hash, expires_at) "
                        "VALUES (%s, 'race@example.com', ARRAY['analyst'], %s, now() + interval '1 day')",
                        (db["a"], digest))
        results, barrier = [], threading.Barrier(2)

        def attempt():
            conn = psycopg2.connect(db["urls"]["app"])
            try:
                barrier.wait()
                results.append(as_org(conn, "", "SELECT user_id FROM scirm_accept_invitation(%s, 'Racer', 'h')",
                                      (digest,)))
            finally:
                conn.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        accepted = [r for r in results if isinstance(r, list) and r]
        assert len(accepted) == 1, results
        assert as_org(db["app"], db["a"], "SELECT count(*) FROM users WHERE email = 'race@example.com'") == [(1,)]



def test_feedback_is_tenant_scoped(db):
    """Migration 016: ratings are visible and writable only inside their own organization."""
    insert = ("INSERT INTO feedback (organization_id, user_id, target_type, target_id, verdict) "
              "VALUES (%s, 'u1', 'answer', 'rls-answer', 'useful')")
    assert as_org(db["app"], db["a"], insert, (db["a"],)) == 1
    assert isinstance(as_org(db["app"], db["b"], insert, (db["a"],)), psycopg2.errors.InsufficientPrivilege)
    assert as_org(db["app"], db["b"], "SELECT count(*) FROM feedback WHERE target_id = 'rls-answer'") == [(0,)]
    assert as_org(db["app"], db["a"], "SELECT count(*) FROM feedback WHERE target_id = 'rls-answer'") == [(1,)]
    assert as_org(db["app"], db["b"], "DELETE FROM feedback WHERE target_id = 'rls-answer'") == 0
    bad = as_org(db["app"], db["a"], "INSERT INTO feedback (organization_id, user_id, target_type, target_id, verdict) "
                                     "VALUES (%s, 'u1', 'answer', 'x', 'great')", (db["a"],))
    assert isinstance(bad, psycopg2.errors.CheckViolation)

class TestApiKeys:
    """Migration 019: keys are tenant-scoped; the pre-tenant lookup finds only live keys."""

    def _key(self, db, org, digest, **extra):
        cols = ", ".join(["organization_id", "name", "prefix", "key_hash", *extra])
        marks = ", ".join(["%s"] * (4 + len(extra)))
        return as_org(db["app"], org, f"INSERT INTO api_keys ({cols}) VALUES ({marks})",
                      (org, "k", "scirm_ABCDEFGH", digest, *extra.values()))

    def test_tenant_scoped(self, db):
        assert self._key(db, db["a"], "a" * 64) == 1
        # Org B cannot create a key in org A's name.
        into_a = as_org(db["app"], db["b"], "INSERT INTO api_keys (organization_id, name, prefix, key_hash) "
                        "VALUES (%s, 'k', 'scirm_ABCDEFGH', %s)", (db["a"], "d" * 64))
        assert isinstance(into_a, psycopg2.errors.InsufficientPrivilege)
        assert as_org(db["app"], db["b"], "SELECT count(*) FROM api_keys WHERE key_hash = %s", ("a" * 64,)) == [(0,)]
        assert as_org(db["app"], db["b"], "UPDATE api_keys SET revoked_at = now() WHERE key_hash = %s", ("a" * 64,)) == 0

    def test_lookup_works_before_any_tenant_is_known_and_flags_dead_keys(self, db):
        self._key(db, db["a"], "e" * 64)
        self._key(db, db["a"], "f" * 64, revoked_at="2026-01-01T00:00:00Z")
        self._key(db, db["a"], "0" * 64, expires_at="2020-01-01T00:00:00Z")
        lookup = "SELECT organization_id::text, live FROM scirm_api_key_lookup(%s)"
        assert as_org(db["app"], "", lookup, ("e" * 64,)) == [(db["a"], True)]
        assert as_org(db["app"], "", lookup, ("f" * 64,)) == [(db["a"], False)]
        assert as_org(db["app"], "", lookup, ("0" * 64,)) == [(db["a"], False)]
        assert as_org(db["app"], "", lookup, ("7" * 64,)) == []

    def test_only_read_scope_and_hashes_are_accepted(self, db):
        bad_scope = as_org(db["app"], db["a"], "INSERT INTO api_keys (organization_id, name, prefix, key_hash, scopes) "
                           "VALUES (%s, 'k', 'scirm_ABCDEFGH', %s, '{write}')", (db["a"], "1" * 64))
        assert isinstance(bad_scope, psycopg2.errors.CheckViolation)
        assert isinstance(self._key(db, db["a"], "not-a-hash"), psycopg2.errors.CheckViolation)


def test_webhook_and_report_tables_are_tenant_scoped_with_forced_rls(db):
    """Migrations 020 and 021: these tables force row-level security; another org sees nothing."""
    tables = ("webhooks", "webhook_events", "webhook_deliveries", "notification_state", "report_schedules",
              "sso_configs")
    with db["owner"].cursor() as cur:
        cur.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)",
                    (list(tables),))
        flags = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    assert flags == {t: (True, True) for t in tables}
    insert = ("INSERT INTO webhook_events (organization_id, type, dedupe_key, payload) "
              "VALUES (%s, 'ping', %s, '{}')")
    assert as_org(db["app"], db["a"], insert, (db["a"], "rls-ping")) == 1
    assert isinstance(as_org(db["app"], db["b"], insert, (db["a"], "rls-ping-2")), psycopg2.errors.InsufficientPrivilege)
    assert as_org(db["app"], db["b"], "SELECT count(*) FROM webhook_events WHERE dedupe_key = 'rls-ping'") == [(0,)]
    duplicate = as_org(db["app"], db["a"], insert, (db["a"], "rls-ping"))
    assert isinstance(duplicate, psycopg2.errors.UniqueViolation)


def test_migrations_downgrade_and_reapply(db):
    """The whole chain must round-trip, so a bad release can be rolled back."""
    env = dict(os.environ, DATABASE_URL=db["urls"]["owner"])
    alembic = [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini")]
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run(alembic + args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stderr[-2000:]
