"""
Regression tests for authentication, authorization and tenant isolation.

Each test pins down a specific vulnerability found in the October 2026 review
so it cannot silently return.
"""

import os
import subprocess
import sys

from pathlib import Path

import jwt as pyjwt
import httpx
import pytest
from starlette.websockets import WebSocketDisconnect

# Defined here rather than imported from conftest: sibling test folders each have
# a conftest.py, and "from conftest import" would resolve to whichever loaded first.
ROOT = Path(__file__).resolve().parents[2]
ORG_1 = "a0000000-0000-0000-0000-000000000001"
ORG_2 = "a0000000-0000-0000-0000-000000000002"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestLogin:
    def test_dev_password_login_succeeds(self, login):
        response = login("sarah.chen@pharmacorp.com")
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_old_hardcoded_password_rejected(self, login):
        assert login("sarah.chen@pharmacorp.com", "scirm-dev-" + "2026").status_code == 401

    def test_unknown_user_rejected(self, login):
        assert login("nobody@example.com").status_code == 401


class TestTokenTypes:
    def test_refresh_token_rejected_as_bearer(self, client, sarah):
        assert client.get("/api/v1/suppliers", headers=bearer(sarah["refresh_token"])).status_code == 401

    def test_token_signed_with_old_public_secret_rejected(self, client):
        forged = pyjwt.encode(
            {"sub": "x", "roles": ["admin"], "org_id": ORG_1, "type": "access", "exp": 9999999999},
            "INSECURE-DEV-ONLY-CHANGE-ME", algorithm="HS256",
        )
        assert client.get("/api/v1/suppliers", headers=bearer(forged)).status_code == 401

    def test_token_without_type_claim_rejected(self, client, apps):
        token = apps["gateway"].create_access_token({"sub": "x", "roles": ["admin"], "org_id": ORG_1, "type": None})
        assert client.get("/api/v1/suppliers", headers=bearer(token)).status_code == 401

    def test_access_token_without_identity_claims_rejected(self, client, apps):
        token = apps["gateway"].create_access_token({"sub": "x"})
        assert client.get("/api/v1/suppliers", headers=bearer(token)).status_code == 401

    def test_refresh_endpoint_issues_access_token(self, client, sarah):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": sarah["refresh_token"]})
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_refresh_endpoint_rejects_access_token(self, client, sarah):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": sarah["access_token"]})
        assert response.status_code == 401


class TestMFA:
    """Uses Marcus so enrolling MFA does not affect other tests' logins."""

    EMAIL = "marcus.rodriguez@pharmacorp.com"

    @pytest.fixture(scope="class")
    def enrolled(self, client, login):
        tokens = login(self.EMAIL).json()
        secret = client.post("/api/v1/auth/mfa/setup", headers=bearer(tokens["access_token"])).json()["secret"]
        challenge = login(self.EMAIL).json()
        return {"secret": secret, "challenge": challenge, "tokens": tokens}

    def test_login_returns_mfa_challenge_once_enrolled(self, enrolled):
        assert enrolled["challenge"].get("mfa_required") is True
        assert "access_token" not in enrolled["challenge"]

    def test_mfa_pending_token_rejected_as_bearer(self, client, enrolled):
        mfa_token = enrolled["challenge"]["mfa_token"]
        assert client.get("/api/v1/suppliers", headers=bearer(mfa_token)).status_code == 401

    def test_verify_requires_genuine_mfa_token(self, client, enrolled):
        from libs.common.auth import generate_totp
        code = generate_totp(enrolled["secret"])
        response = client.post("/api/v1/auth/mfa/verify",
                               json={"totp_code": code, "mfa_token": enrolled["tokens"]["refresh_token"]})
        assert response.status_code == 401

    def test_verify_rejects_wrong_code(self, client, enrolled):
        from libs.common.auth import generate_totp
        wrong = "111111" if generate_totp(enrolled["secret"]) != "111111" else "222222"
        response = client.post("/api/v1/auth/mfa/verify",
                               json={"totp_code": wrong, "mfa_token": enrolled["challenge"]["mfa_token"]})
        assert response.status_code == 401

    def test_verify_with_token_and_code_succeeds(self, client, enrolled):
        from libs.common.auth import generate_totp
        response = client.post("/api/v1/auth/mfa/verify",
                               json={"totp_code": generate_totp(enrolled["secret"]),
                                     "mfa_token": enrolled["challenge"]["mfa_token"]})
        assert response.status_code == 200
        assert "access_token" in response.json()


class TestSignup:
    def test_signup_ignores_client_supplied_organization(self, client):
        response = client.post("/api/v1/auth/signup", json={
            "email": "tenant-hop@example.com", "password": "longenough1",
            "name": "Hopper", "organization_id": ORG_1,
        })
        assert response.status_code == 200
        claims = pyjwt.decode(response.json()["access_token"], options={"verify_signature": False})
        assert claims["org_id"] not in (ORG_1, ORG_2)
        suppliers = client.get("/api/v1/suppliers", headers=bearer(response.json()["access_token"])).json()
        assert suppliers["suppliers"] == []

    def test_password_is_stored_hashed_and_verifies(self, client, login, apps):
        client.post("/api/v1/auth/signup", json={"email": "hashed@example.com", "password": "longenough1", "name": "H"})
        assert "longenough1" not in str(apps["gateway"]._registered_users["hashed@example.com"])
        assert login("hashed@example.com", "longenough1").status_code == 200
        assert login("hashed@example.com", "wrong-password").status_code == 401

    def test_overlong_password_is_a_clean_400(self, client, login):
        response = client.post("/api/v1/auth/signup", json={"email": "long@example.com", "password": "p" * 100, "name": "L"})
        assert response.status_code == 400
        assert login("hashed@example.com", "p" * 100).status_code == 401


class TestOAuthMock:
    def test_unknown_provider_rejected(self, client):
        assert client.get("/api/v1/auth/oauth/authorize", params={"provider": "evil.com/x?"}).status_code == 400

    def test_foreign_redirect_uri_rejected(self, client):
        response = client.get("/api/v1/auth/oauth/authorize", params={"redirect_uri": "https://evil.com/cb"})
        assert response.status_code == 400

    def test_state_is_random(self, client):
        first = client.get("/api/v1/auth/oauth/authorize").json()["state"]
        second = client.get("/api/v1/auth/oauth/authorize").json()["state"]
        assert first != second


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_each_org_sees_only_its_suppliers(self, client, sarah, lisa):
        org1 = client.get("/api/v1/suppliers", headers=bearer(sarah["access_token"])).json()["suppliers"]
        org2 = client.get("/api/v1/suppliers", headers=bearer(lisa["access_token"])).json()["suppliers"]
        assert org1 and {s["organization_id"] for s in org1} == {ORG_1}
        assert org2 and {s["organization_id"] for s in org2} == {ORG_2}

    def test_org_id_query_parameter_cannot_select_another_tenant(self, client, lisa):
        response = client.get("/api/v1/suppliers", params={"org_id": ORG_1}, headers=bearer(lisa["access_token"]))
        assert {s["organization_id"] for s in response.json()["suppliers"]} == {ORG_2}

    def test_cross_tenant_supplier_read_blocked(self, client, sarah, lisa):
        other = client.get("/api/v1/suppliers", headers=bearer(sarah["access_token"])).json()["suppliers"][0]["id"]
        assert client.get(f"/api/v1/suppliers/{other}", headers=bearer(lisa["access_token"])).status_code == 404

    def test_cross_tenant_supplier_update_blocked(self, client, apps, sarah, lisa):
        other = client.get("/api/v1/suppliers", headers=bearer(sarah["access_token"])).json()["suppliers"][0]["id"]
        response = client.put(f"/api/v1/suppliers/{other}", json={"name": "pwned"}, headers=bearer(lisa["access_token"]))
        assert response.status_code != 200
        owner_view = client.get(f"/api/v1/suppliers/{other}", headers=bearer(sarah["access_token"])).json()
        assert owner_view["name"] != "pwned"

    def test_created_supplier_is_forced_into_callers_org(self, client, sarah):
        response = client.post("/api/v1/suppliers", json={"name": "New Co", "organization_id": ORG_2},
                               headers=bearer(sarah["access_token"]))
        assert response.status_code == 200
        assert response.json()["organization_id"] == ORG_1

    def test_supplier_cannot_be_moved_to_another_org(self, client, apps, sarah):
        own = client.get("/api/v1/suppliers", headers=bearer(sarah["access_token"])).json()["suppliers"][0]["id"]
        client.put(f"/api/v1/suppliers/{own}", json={"organization_id": ORG_2}, headers=bearer(sarah["access_token"]))
        owner_view = client.get(f"/api/v1/suppliers/{own}", headers=bearer(sarah["access_token"])).json()
        assert owner_view["organization_id"] == ORG_1

    def test_risks_are_scoped_to_their_org(self, client, sarah, lisa):
        risk_id = client.post("/api/v1/risks", json={"title": "Org1-only risk"},
                              headers=bearer(sarah["access_token"])).json()["id"]
        assert client.get(f"/api/v1/risks/{risk_id}", headers=bearer(sarah["access_token"])).status_code == 200
        assert client.get(f"/api/v1/risks/{risk_id}", headers=bearer(lisa["access_token"])).status_code == 404
        listed = client.get("/api/v1/risks", headers=bearer(lisa["access_token"])).json()["risks"]
        assert all(r["id"] != risk_id for r in listed)
        assert "Org1-only risk" not in client.get("/api/v1/export/risks", headers=bearer(lisa["access_token"])).text

    def test_risk_history_route_is_reachable(self, client, lisa):
        response = client.get("/api/v1/risks/history", headers=bearer(lisa["access_token"]))
        assert response.status_code == 200
        assert "history" in response.json()

    def test_procurement_actions_are_scoped_to_their_org(self, client, sarah, lisa):
        response = client.post("/api/v1/procurement/evaluate",
                               json={"suppliers": [{"name": "Supplier Gamma", "risk_score": 90}]},
                               headers=bearer(lisa["access_token"]))
        assert response.status_code == 200
        org2 = client.get("/api/v1/procurement/actions", headers=bearer(lisa["access_token"])).json()["actions"]
        org1 = client.get("/api/v1/procurement/actions", headers=bearer(sarah["access_token"])).json()["actions"]
        assert org2 and all(a["organization_id"] == ORG_2 for a in org2)
        assert all(a["organization_id"] != ORG_2 for a in org1)

    def test_chat_answers_with_callers_org_data_only(self, client, lisa):
        response = client.post("/api/v1/chat", json={"message": "list suppliers"}, headers=bearer(lisa["access_token"]))
        assert response.status_code == 200
        assert "Supplier Delta" in response.text
        assert "Supplier Alpha" not in response.text

    def test_user_jwt_is_not_forwarded_and_org_header_is(self, client, apps, sarah):
        router = apps["router"]
        router.seen_headers.clear()
        client.get("/api/v1/suppliers", headers=bearer(sarah["access_token"]))
        assert router.seen_headers
        assert all("authorization" not in h for h in router.seen_headers)
        assert all(h.get("x-org-id") == ORG_1 for h in router.seen_headers)

    def test_coordinator_rejects_calls_without_org_header(self, apps):
        from fastapi.testclient import TestClient
        assert TestClient(apps["coordinator"].app).get("/suppliers").status_code == 401


# ---------------------------------------------------------------------------
# Authorization (roles)
# ---------------------------------------------------------------------------

class TestPublicSignals:
    """Public records are shared; which of a tenant's suppliers they concern is not."""

    SUN = "c0000000-0000-0000-0000-000000000103"  # org 1 demo supplier, a real company name

    @pytest.fixture(scope="class")
    def ingested(self, client, sarah):
        response = client.post("/api/v1/intelligence/ingest", headers=bearer(sarah["access_token"]))
        assert response.status_code == 200, response.text
        assert response.json()["documents_ingested"] > 0

    def test_supplier_signals_show_public_records_for_own_supplier(self, client, sarah, ingested):
        response = client.get(f"/api/v1/suppliers/{self.SUN}/signals", headers=bearer(sarah["access_token"]))
        assert response.status_code == 200, response.text
        incidents = response.json()["incidents"]
        assert incidents and all(m["kind"] == "incident" and m["signal"]["url"] for m in incidents)

    def test_another_orgs_supplier_signals_are_not_found(self, client, lisa, ingested):
        response = client.get(f"/api/v1/suppliers/{self.SUN}/signals", headers=bearer(lisa["access_token"]))
        assert response.status_code == 404

    def test_overview_lists_only_own_suppliers(self, client, sarah, lisa, ingested):
        org2 = client.get("/api/v1/signals/suppliers", headers=bearer(lisa["access_token"])).json()["suppliers"]
        # The recorded Sun Pharma recalls are from 2017 and 2023, outside the default 365-day window.
        org1 = client.get("/api/v1/signals/suppliers", params={"since_days": 3650},
                          headers=bearer(sarah["access_token"])).json()["suppliers"]
        assert {r["supplier_name"] for r in org2} == {"Supplier Delta", "Supplier Epsilon"}
        assert any(r["supplier_id"] == self.SUN and r["incidents"] for r in org1)

    def test_only_the_tenants_suppliers_reach_the_ingestion_service(self, client, apps, lisa, ingested, monkeypatch):
        sent = []
        original = apps["ingestion"].matching.match_all

        def spy(suppliers, signals, **kwargs):
            sent.extend(s.get("name") for s in suppliers)
            return original(suppliers, signals, **kwargs)

        monkeypatch.setattr(apps["ingestion"].matching, "match_all", spy)
        client.get("/api/v1/signals/suppliers", headers=bearer(lisa["access_token"]))
        assert set(sent) == {"Supplier Delta", "Supplier Epsilon"}

    def test_ask_about_own_supplier_cites_records(self, client, sarah, ingested):
        response = client.post(f"/api/v1/suppliers/{self.SUN}/ask", json={"question": "Any recalls?"},
                               headers=bearer(sarah["access_token"]))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "answered" and all(c["citations"] for c in body["claims"])

    def test_cannot_ask_about_another_orgs_supplier(self, client, lisa, ingested):
        response = client.post(f"/api/v1/suppliers/{self.SUN}/ask", json={"question": "Any recalls?"},
                               headers=bearer(lisa["access_token"]))
        assert response.status_code == 404

    def test_matching_outage_is_a_503_not_an_empty_answer(self, client, apps, sarah, monkeypatch):
        original = apps["router"].handle_async_request

        async def routed(request):
            if request.url.port == 8008:  # the ingestion service is down
                raise httpx.ConnectError("connection refused", request=request)
            return await original(request)

        monkeypatch.setattr(apps["router"], "handle_async_request", routed)
        response = client.get(f"/api/v1/suppliers/{self.SUN}/signals", headers=bearer(sarah["access_token"]))
        assert response.status_code == 503


class TestRoles:
    def test_read_only_role_cannot_create_supplier(self, client, auditor):
        assert client.post("/api/v1/suppliers", json={"name": "x"}, headers=bearer(auditor["access_token"])).status_code == 403

    def test_read_only_role_cannot_create_risk(self, client, auditor):
        assert client.post("/api/v1/risks", json={"title": "x"}, headers=bearer(auditor["access_token"])).status_code == 403

    def test_read_only_role_can_read(self, client, auditor):
        assert client.get("/api/v1/suppliers", headers=bearer(auditor["access_token"])).status_code == 200


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

class TestAudit:
    def test_writes_are_audited_with_actor_and_outcome(self, client, sarah):
        created = client.post("/api/v1/suppliers", json={"name": "Audited Co"}, headers=bearer(sarah["access_token"]))
        assert created.status_code == 200
        entries = client.get("/api/v1/audit", headers=bearer(sarah["access_token"])).json()["entries"]
        match = [e for e in entries if e["action"] == "POST /api/v1/suppliers" and e["status_code"] == 200]
        assert match, entries[:3]
        assert match[0]["actor"] == "sarah.chen@pharmacorp.com"
        assert match[0]["resource_type"] == "suppliers"

    def test_rejected_writes_are_audited_too(self, client, auditor):
        client.post("/api/v1/suppliers", json={"name": "x"}, headers=bearer(auditor["access_token"]))
        entries = client.get("/api/v1/audit", headers=bearer(auditor["access_token"])).json()["entries"]
        assert any(e["action"] == "POST /api/v1/suppliers" and e["status_code"] == 403 for e in entries)

    def test_audit_log_is_tenant_scoped(self, client, sarah, lisa):
        client.post("/api/v1/suppliers", json={"name": "Org1 Only Co"}, headers=bearer(sarah["access_token"]))
        lisa_entries = client.get("/api/v1/audit", headers=bearer(lisa["access_token"])).json()["entries"]
        assert all(e.get("actor") != "sarah.chen@pharmacorp.com" for e in lisa_entries)

    def test_sign_ins_are_audited_with_the_account_email(self, client, login, sarah):
        login("sarah.chen@pharmacorp.com")
        entries = client.get("/api/v1/audit", headers=bearer(sarah["access_token"])).json()["entries"]
        assert any(e["action"] == "auth.login" and e["actor"] == "sarah.chen@pharmacorp.com" for e in entries)

    def test_only_admins_and_auditors_read_the_audit_log(self, client, apps):
        analyst = apps["gateway"].create_access_token({"sub": "b0000000-0000-0000-0000-0000000000aa",
                                                       "roles": ["analyst"], "org_id": ORG_1})
        assert client.get("/api/v1/audit", headers=bearer(analyst)).status_code == 403


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

class TestWebSocket:
    def test_rejects_invalid_token(self, client):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"token": "garbage"})
                ws.receive_json()

    def test_accepts_valid_token(self, client, lisa):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"token": lisa["access_token"]})
            assert ws.receive_json().get("event") == "authenticated"

    def test_rejects_foreign_origin(self, client, lisa):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": "https://evil.com"}) as ws:
                ws.send_json({"token": lisa["access_token"]})
                ws.receive_json()


# ---------------------------------------------------------------------------
# Fail-closed configuration (each check runs in a fresh interpreter)
# ---------------------------------------------------------------------------

def _import_in_subprocess(module: str, env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("JWT_SECRET_KEY", "SERVICE_API_KEY", "DEV_PASSWORD")}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, r'{ROOT}'); import {module}"],
        env=env, capture_output=True, text=True, timeout=120,
    )


# Production refuses the in-memory store; these processes get a Postgres URL that is
# never contacted (the engine connects lazily) so the other checks can run.
PROD_DB = {"STORE_BACKEND": "postgres", "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/unused"}


class TestFailClosedConfig:
    def test_production_refuses_in_memory_store(self):
        result = _import_in_subprocess("libs.common.store; libs.common.store.create_store()",
                                       {"ENVIRONMENT": "production", "STORE_BACKEND": "memory"})
        assert result.returncode != 0 and "not allowed" in result.stderr

    def test_production_requires_jwt_secret(self):
        result = _import_in_subprocess("libs.common.auth", {"ENVIRONMENT": "production"})
        assert result.returncode != 0 and "JWT_SECRET_KEY must be set" in result.stderr

    def test_production_rejects_short_jwt_secret(self):
        result = _import_in_subprocess("libs.common.auth", {"ENVIRONMENT": "production", "JWT_SECRET_KEY": "short"})
        assert result.returncode != 0 and "at least 32 characters" in result.stderr

    def test_production_requires_service_key(self):
        result = _import_in_subprocess("libs.common.tenancy", {"ENVIRONMENT": "production"})
        assert result.returncode != 0 and "SERVICE_API_KEY must be set" in result.stderr

    def test_production_gateway_has_no_demo_accounts(self):
        code = (
            f"import sys, importlib.util; sys.path.insert(0, r'{ROOT}');"
            f"s = importlib.util.spec_from_file_location('gw', r'{ROOT / 'apps/api-gateway/main.py'}');"
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print(len(m.DEV_USERS))"
        )
        env = {k: v for k, v in os.environ.items() if k not in ("DEV_PASSWORD",)}
        env.update({"ENVIRONMENT": "production", "JWT_SECRET_KEY": "k" * 40, "SERVICE_API_KEY": "svc-key", **PROD_DB})
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().endswith("0")

    def test_service_key_enforced_when_configured(self):
        code = (
            f"import sys, importlib.util; sys.path.insert(0, r'{ROOT}');"
            f"s = importlib.util.spec_from_file_location('c', r'{ROOT / 'services/coordinator/main.py'}');"
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m);"
            "from fastapi.testclient import TestClient; c = TestClient(m.app);"
            "h = {'X-Org-Id': 'o'}; body = {'affected_suppliers': []};"
            "print(c.post('/scenarios/simulate', json=body, headers=h).status_code,"
            " c.post('/scenarios/simulate', json=body, headers={**h, 'X-Service-Key': 'bad'}).status_code,"
            " c.post('/scenarios/simulate', json=body, headers={**h, 'X-Service-Key': 'svc-key'}).status_code)"
        )
        env = dict(os.environ, ENVIRONMENT="production", SERVICE_API_KEY="svc-key", **PROD_DB)
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        # 400 = authenticated and reached the handler (which rejects the empty scenario).
        assert result.stdout.split()[-3:] == ["403", "403", "400"]
