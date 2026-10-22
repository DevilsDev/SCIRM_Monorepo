"""
API keys for the read-only public API: admin-only management, a default-deny route
allowlist, revocation that takes effect immediately, and audited refusals.
Runs on both backends, like the rest of the security suite.
"""

import pytest

from libs.common.store import is_api_key


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def key(client, sarah):
    created = client.post("/api/v1/org/api-keys", json={"name": "ERP sync"}, headers=bearer(sarah["access_token"]))
    assert created.status_code == 200, created.text
    body = created.json()
    assert is_api_key(body["key"]) and body["key"].startswith(body["api_key"]["prefix"])
    return body


class TestManagement:
    def test_only_admins(self, client, auditor):
        assert client.post("/api/v1/org/api-keys", json={"name": "x"},
                           headers=bearer(auditor["access_token"])).status_code == 403
        assert client.get("/api/v1/org/api-keys", headers=bearer(auditor["access_token"])).status_code == 403

    def test_the_key_is_shown_once_and_listed_by_prefix(self, client, sarah, key):
        listed = client.get("/api/v1/org/api-keys", headers=bearer(sarah["access_token"])).json()["api_keys"]
        mine = next(k for k in listed if k["id"] == key["api_key"]["id"])
        assert mine["prefix"] == key["api_key"]["prefix"] and mine["created_by"] == "sarah.chen@pharmacorp.com"
        assert all(key["key"] not in str(k) for k in listed) and "key_hash" not in mine

    def test_another_organization_cannot_see_or_revoke_it(self, client, lisa, key):
        listed = client.get("/api/v1/org/api-keys", headers=bearer(lisa["access_token"])).json()["api_keys"]
        assert all(k["id"] != key["api_key"]["id"] for k in listed)
        assert client.delete(f"/api/v1/org/api-keys/{key['api_key']['id']}",
                             headers=bearer(lisa["access_token"])).status_code == 404


class TestPublicApi:
    def test_reads_allowed_routes_in_its_own_organization(self, client, sarah, lisa, key):
        response = client.get("/api/v1/suppliers", headers=bearer(key["key"]))
        assert response.status_code == 200, response.text
        ids = {s["id"] for s in response.json()["suppliers"]}
        own = {s["id"] for s in client.get("/api/v1/suppliers", headers=bearer(sarah["access_token"])).json()["suppliers"]}
        other = {s["id"] for s in client.get("/api/v1/suppliers", headers=bearer(lisa["access_token"])).json()["suppliers"]}
        assert ids and ids == own and not ids & other
        assert client.get("/api/v1/intelligence/sources", headers={"X-API-Key": key["key"]}).status_code == 200

    @pytest.mark.parametrize("method,path", [
        ("GET", "/api/v1/audit"), ("GET", "/api/v1/audit/export"), ("GET", "/api/v1/org/members"),
        ("GET", "/api/v1/org/api-keys"), ("GET", "/api/v1/auth/mfa"), ("GET", "/api/v1/integrations/sap"),
        ("POST", "/api/v1/suppliers"), ("POST", "/api/v1/org/invitations"), ("POST", "/api/v1/auth/mfa/setup"),
        ("DELETE", "/api/v1/org/api-keys/x"), ("GET", "/api/v1/no-such-route"),
    ])
    def test_everything_else_is_refused(self, client, key, method, path):
        response = client.request(method, path, headers=bearer(key["key"]), json={})
        assert response.status_code == 403, (path, response.status_code)

    def test_the_key_cannot_write_through_an_allowed_path_with_another_method(self, client, key):
        assert client.post("/api/v1/suppliers/abc/ask", headers=bearer(key["key"]),
                           json={"question": "anything?"}).status_code == 403

    def test_unknown_and_revoked_keys_get_401(self, client, sarah, key):
        assert client.get("/api/v1/suppliers", headers=bearer("scirm_AAAAAAAA_" + "x" * 43)).status_code == 401
        assert client.delete(f"/api/v1/org/api-keys/{key['api_key']['id']}",
                             headers=bearer(sarah["access_token"])).status_code == 200
        assert client.get("/api/v1/suppliers", headers=bearer(key["key"])).status_code == 401
        # Still visible to the organization: a revoked key that is still in use.
        log = client.get("/api/v1/audit", params={"failed": "true", "limit": 20},
                         headers=bearer(sarah["access_token"])).json()["entries"]
        assert any(e["action"] == "api_key.refused" and e["status_code"] == 401
                   and e["actor"] == f"api-key:{key['api_key']['prefix']}" for e in log)

    def test_use_is_recorded_and_refusals_are_audited_by_prefix(self, client, sarah, key):
        client.get("/api/v1/suppliers", headers=bearer(key["key"]))
        client.get("/api/v1/audit", headers=bearer(key["key"]))
        listed = client.get("/api/v1/org/api-keys", headers=bearer(sarah["access_token"])).json()["api_keys"]
        assert next(k for k in listed if k["id"] == key["api_key"]["id"])["last_used_at"]
        log = client.get("/api/v1/audit", params={"category": "access", "limit": 50},
                         headers=bearer(sarah["access_token"])).json()["entries"]
        refused = [e for e in log if e["action"] == "api_key.refused"]
        assert refused and refused[0]["actor"] == f"api-key:{key['api_key']['prefix']}"
        assert all(key["key"] not in str(e) for e in log)
        assert any(e["action"] == "api_key.created" for e in log)


def test_an_expired_key_is_refused(client, apps, sarah):
    import asyncio
    store = apps["gateway"].audit_store
    _, key = asyncio.run(store.create_api_key("a0000000-0000-0000-0000-000000000001", "old", "t",
                                              expires_at="2020-01-01T00:00:00+00:00"))
    assert client.get("/api/v1/suppliers", headers=bearer(key)).status_code == 401
