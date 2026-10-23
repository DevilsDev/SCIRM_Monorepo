"""
Single sign-on (OpenID Connect) against a fake identity provider with its own RSA key:
the full flow, account linking by (issuer, subject), the one-time handoff, enforcement, and
the token checks that keep it safe. Runs on both backends, like the rest of the security suite.
"""

import base64
import hashlib
import json
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from libs.common import oidc

ISSUER = "https://idp.example.com/realms/acme"
CLIENT_ID, CLIENT_SECRET = "scirm-app", "client-secret-123"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class FakeIdp:
    """Discovery, key set and token endpoint. The test plays the browser and the login page."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwks = {"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}
        self.codes = {}
        self.token_requests = []
        self.issuer_in_discovery = ISSUER

    def sign(self, claims, alg="RS256", kid="k1", key=None):
        if alg == "HS256":
            return jwt.encode(claims, "shared", algorithm="HS256", headers={"kid": kid})
        return jwt.encode(claims, key or self.key, algorithm=alg, headers={"kid": kid})

    def claims(self, sub, email, nonce, **extra):
        now = int(time.time())
        return {"iss": ISSUER, "aud": CLIENT_ID, "sub": sub, "email": email, "email_verified": True,
                "nonce": nonce, "iat": now, "exp": now + 300, **extra}

    def transport(self):
        def handle(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json={"issuer": self.issuer_in_discovery,
                                                 "authorization_endpoint": "https://idp.example.com/auth",
                                                 "token_endpoint": "https://idp.example.com/token",
                                                 "jwks_uri": "https://idp.example.com/jwks"})
            if path == "/jwks":
                return httpx.Response(200, json=self.jwks)
            if path == "/token":
                form = parse_qs(request.content.decode())
                self.token_requests.append({"auth": request.headers.get("authorization"), **form})
                issued = self.codes.pop(form["code"][0], None)
                expected = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
                if not issued or request.headers.get("authorization") != f"Basic {expected}":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest())
                if challenge.decode().rstrip("=") != issued["challenge"]:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={"id_token": issued["id_token"], "token_type": "Bearer"})
            return httpx.Response(404)
        return httpx.MockTransport(handle)


@pytest.fixture
def idp(monkeypatch, client):
    fake = FakeIdp()
    monkeypatch.setattr(oidc, "transport_factory", fake.transport)
    oidc._cache.clear()
    client.cookies.clear()
    yield fake
    oidc._cache.clear()
    client.cookies.clear()


@pytest.fixture
def configured(client, sarah, idp):
    saved = client.put("/api/v1/org/sso", json={"issuer": ISSUER, "client_id": CLIENT_ID,
                                                "client_secret": CLIENT_SECRET}, headers=bearer(sarah["access_token"]))
    assert saved.status_code == 200, saved.text
    yield saved.json()
    client.delete("/api/v1/org/sso", headers=bearer(sarah["access_token"]))


@pytest.fixture
def member(client, sarah):
    email = f"sso-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post("/api/v1/org/invitations", json={"email": email, "roles": ["analyst"]},
                          headers=bearer(sarah["access_token"]))
    token = invited.json()["invite_url"].split("#", 1)[1]
    client.post("/api/v1/invitations/accept", json={"token": token, "name": "S", "password": "a-good-password"})
    return email


def start(client, email, next_path="/suppliers"):
    response = client.get("/api/v1/auth/sso/start", params={"email": email, "next": next_path}, follow_redirects=False)
    assert response.status_code == 302, response.text
    return response


def sign_in(client, idp, email, *, sub=None, claims_extra=None, tamper=None, state_override=None):
    """Start, 'log in' at the fake provider, and return the callback response."""
    location = urlsplit(start(client, email).headers["location"])
    q = {k: v[0] for k, v in parse_qs(location.query).items()}
    claims = {**idp.claims(sub or f"idp-{email}", email, q["nonce"]), **(claims_extra or {})}
    id_token = tamper(claims) if tamper else idp.sign(claims)
    idp.codes["code-1"] = {"challenge": q["code_challenge"], "id_token": id_token}
    return client.get("/api/v1/auth/sso/callback", params={"code": "code-1", "state": state_override or q["state"]},
                      follow_redirects=False), q


def handoff(callback):
    location = callback.headers["location"]
    assert "/sso/complete#code=" in location, location
    return parse_qs(location.split("#", 1)[1])["code"][0]


class TestFlow:
    def test_full_sign_in(self, client, idp, configured, member):
        callback, q = sign_in(client, idp, member)
        assert q["code_challenge_method"] == "S256" and q["response_mode"] == "query" and q["login_hint"] == member
        assert q["redirect_uri"] == "http://localhost:8000/api/v1/auth/sso/callback"
        code = handoff(callback)
        assert "next=/suppliers" in callback.headers["location"]
        tokens = client.post("/api/v1/auth/sso/exchange", json={"code": code})
        assert tokens.status_code == 200, tokens.text
        me = jwt.decode(tokens.json()["access_token"], options={"verify_signature": False})
        assert me["email"] == member
        assert client.post("/api/v1/auth/sso/exchange", json={"code": code}).status_code == 400  # once
        assert idp.token_requests[-1]["grant_type"] == ["authorization_code"]

    def test_the_account_is_linked_to_the_subject(self, client, idp, configured, member):
        handoff(sign_in(client, idp, member, sub="subject-A")[0])
        client.cookies.clear()
        # Same email, another subject (a reassigned email at the provider): refused.
        assert "sso=failed" in sign_in(client, idp, member, sub="subject-B")[0].headers["location"]
        client.cookies.clear()
        # The linked subject works even if the provider now reports another email.
        callback, _ = sign_in(client, idp, member, sub="subject-A", claims_extra={"email": "renamed@example.com"})
        assert "/sso/complete#code=" in callback.headers["location"]

    def test_unknown_accounts_and_other_organizations_get_the_same_answer(self, client, idp, configured, lisa):
        for email in (f"nobody-{uuid.uuid4().hex[:6]}@example.com", "lisa.park@medtech.com"):
            response = client.get("/api/v1/auth/sso/start", params={"email": email}, follow_redirects=False)
            assert response.status_code == 302 and response.headers["location"].endswith("/login?sso=unavailable")


class TestRefusals:
    @pytest.mark.parametrize("case", ["wrong_aud", "wrong_iss", "expired", "wrong_nonce", "unverified_email",
                                      "alg_none", "hs256", "unknown_kid", "foreign_key"])
    def test_bad_tokens(self, client, idp, configured, member, case):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tamper = {
            "wrong_aud": lambda c: idp.sign({**c, "aud": "someone-else"}),
            "wrong_iss": lambda c: idp.sign({**c, "iss": "https://evil.example.com"}),
            "expired": lambda c: idp.sign({**c, "exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}),
            "wrong_nonce": lambda c: idp.sign({**c, "nonce": "replayed"}),
            "unverified_email": lambda c: idp.sign({**c, "email_verified": False}),
            "alg_none": lambda c: jwt.encode(c, None, algorithm="none"),
            "hs256": lambda c: idp.sign(c, alg="HS256"),
            "unknown_kid": lambda c: idp.sign(c, kid="nope"),
            "foreign_key": lambda c: idp.sign(c, key=other),
        }[case]
        callback, _ = sign_in(client, idp, member, tamper=tamper)
        assert "/sso/complete" not in callback.headers["location"], case

    def test_wrong_state_and_missing_cookie(self, client, idp, configured, member):
        assert "sso=failed" in sign_in(client, idp, member, state_override="forged")[0].headers["location"]
        client.cookies.clear()
        no_cookie = client.get("/api/v1/auth/sso/callback", params={"code": "x", "state": "y"}, follow_redirects=False)
        assert no_cookie.headers["location"].endswith("sso=expired")

    def test_open_redirects_are_ignored(self, client, idp, configured, member):
        for bad in ("https://evil.example.com", "//evil.example.com", "/\\evil", "javascript:alert(1)"):
            client.cookies.clear()
            location = urlsplit(start(client, member, next_path=bad).headers["location"])
            q = {k: v[0] for k, v in parse_qs(location.query).items()}
            idp.codes["code-1"] = {"challenge": q["code_challenge"],
                                   "id_token": idp.sign(idp.claims(f"idp-{member}", member, q["nonce"]))}
            callback = client.get("/api/v1/auth/sso/callback", params={"code": "code-1", "state": q["state"]},
                                  follow_redirects=False)
            assert callback.headers["location"].endswith("next=/dashboard"), bad

    def test_an_expired_handoff_is_refused(self, client, apps, idp, configured, member):
        import asyncio
        from datetime import datetime, timedelta, timezone
        store = apps["gateway"].audit_store
        account = asyncio.run(store.find_login_user(member))
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        asyncio.run(store.create_sso_handoff(str(account["organization_id"]), str(account["id"]),
                                             hashlib.sha256(b"old-handoff-code-123456").hexdigest(), past))
        assert client.post("/api/v1/auth/sso/exchange", json={"code": "old-handoff-code-123456"}).status_code == 400


class TestConfiguration:
    @pytest.mark.parametrize("issuer", ["https://login.microsoftonline.com/common/v2.0",
                                        "https://login.microsoftonline.com/organizations/v2.0",
                                        "ftp://idp.example.com"])
    def test_bad_issuers_are_refused(self, client, sarah, idp, issuer):
        assert client.put("/api/v1/org/sso", json={"issuer": issuer, "client_id": "c", "client_secret": "s"},
                          headers=bearer(sarah["access_token"])).status_code == 400

    def test_the_issuer_must_match_the_providers_metadata(self, client, sarah, idp):
        idp.issuer_in_discovery = "https://idp.example.com/realms/other"
        assert client.put("/api/v1/org/sso", json={"issuer": ISSUER, "client_id": "c", "client_secret": "s"},
                          headers=bearer(sarah["access_token"])).status_code == 400

    def test_the_first_configuration_needs_a_secret(self, client, sarah, idp):
        assert client.put("/api/v1/org/sso", json={"issuer": ISSUER, "client_id": CLIENT_ID},
                          headers=bearer(sarah["access_token"])).status_code == 400

    def test_only_admins_and_the_secret_is_never_shown(self, client, sarah, auditor, configured):
        assert client.get("/api/v1/org/sso", headers=bearer(auditor["access_token"])).status_code == 403
        shown = client.get("/api/v1/org/sso", headers=bearer(sarah["access_token"])).json()
        assert shown["config"]["client_id"] == CLIENT_ID and CLIENT_SECRET not in json.dumps(shown)

    def test_strict_mode_requires_https(self):
        with pytest.raises(oidc.OidcError):
            oidc.validate_issuer("http://idp.example.com/realms/acme", strict=True)


class TestEnforcement:
    def test_members_must_use_sso_admins_keep_their_password(self, client, login, sarah, idp, configured, member):
        # Turned on later, without re-entering the secret (the stored one is kept).
        on = client.put("/api/v1/org/sso", json={"issuer": ISSUER, "client_id": CLIENT_ID, "enforce": True},
                        headers=bearer(sarah["access_token"]))
        assert on.status_code == 200, on.text
        assert on.json()["config"]["enforce"] is True
        try:
            refused = login(member, "a-good-password")
            assert refused.status_code == 403 and "single sign-on" in refused.json()["detail"]
            assert login("sarah.chen@pharmacorp.com").status_code == 200  # demo admin
            assert login(member, "wrong-password").status_code == 401  # nothing revealed without the password
        finally:
            client.delete("/api/v1/org/sso", headers=bearer(sarah["access_token"]))
        assert login(member, "a-good-password").status_code == 200
