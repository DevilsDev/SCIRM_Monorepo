"""
Two-step sign-in (TOTP) enrollment: a seed stays pending until a code confirms it, it
cannot be replaced or removed with a session alone, and an admin can reset a teammate's.
Runs on both backends, like the rest of the security suite.
"""

import asyncio
import uuid

import jwt
import pytest

from libs.common.auth import generate_totp

PASSWORD = "a-good-password"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wrong(secret: str) -> str:
    return "111111" if generate_totp(secret) != "111111" else "222222"


@pytest.fixture
def member(client, sarah):
    """A fresh stored account in org 1 (PharmaCorp, where Sarah is admin)."""
    email = f"enroll-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post("/api/v1/org/invitations", json={"email": email, "roles": ["analyst"]},
                          headers=bearer(sarah["access_token"]))
    token = invited.json()["invite_url"].split("#", 1)[1]
    tokens = client.post("/api/v1/invitations/accept", json={"token": token, "name": "E", "password": PASSWORD}).json()
    user_id = jwt.decode(tokens["access_token"], options={"verify_signature": False})["sub"]
    return {"email": email, "id": user_id, "h": bearer(tokens["access_token"])}


def enroll(client, member) -> str:
    secret = client.post("/api/v1/auth/mfa/setup", headers=member["h"]).json()["secret"]
    assert client.post("/api/v1/auth/mfa/confirm", json={"totp_code": generate_totp(secret)},
                       headers=member["h"]).status_code == 200
    return secret


class TestEnrollment:
    def test_a_pending_seed_does_not_challenge_sign_in(self, client, login, member):
        client.post("/api/v1/auth/mfa/setup", headers=member["h"])
        signed_in = login(member["email"], PASSWORD).json()
        assert "access_token" in signed_in and not signed_in.get("mfa_required")
        status = client.get("/api/v1/auth/mfa", headers=member["h"]).json()
        assert status["enabled"] is False and status["pending"] is True

    def test_a_wrong_code_does_not_confirm(self, client, login, member):
        secret = client.post("/api/v1/auth/mfa/setup", headers=member["h"]).json()["secret"]
        assert client.post("/api/v1/auth/mfa/confirm", json={"totp_code": wrong(secret)},
                           headers=member["h"]).status_code == 400
        assert not login(member["email"], PASSWORD).json().get("mfa_required")

    def test_confirmed_enrollment_challenges_sign_in(self, client, login, member):
        enroll(client, member)
        assert login(member["email"], PASSWORD).json().get("mfa_required") is True
        assert client.get("/api/v1/auth/mfa", headers=member["h"]).json()["enabled"] is True

    def test_setup_is_refused_while_enabled(self, client, member):
        enroll(client, member)
        assert client.post("/api/v1/auth/mfa/setup", headers=member["h"]).status_code == 409

    def test_disable_needs_a_current_code(self, client, login, member):
        secret = enroll(client, member)
        assert client.post("/api/v1/auth/mfa/disable", json={"totp_code": wrong(secret)},
                           headers=member["h"]).status_code == 400
        assert login(member["email"], PASSWORD).json().get("mfa_required") is True
        assert client.post("/api/v1/auth/mfa/disable", json={"totp_code": generate_totp(secret)},
                           headers=member["h"]).status_code == 200
        assert "access_token" in login(member["email"], PASSWORD).json()

    def test_a_legacy_pending_seed_stays_pending_when_resealed(self, client, login, apps, member):
        # Re-encryption on read rewrites the seed only; it must not switch MFA on.
        store = apps["gateway"].audit_store
        if hasattr(store, "users"):
            store.users[member["id"]].update(mfa_secret="JBSWY3DPEHPK3PXP", mfa_enabled=False)
        else:
            asyncio.run(store._exec("a0000000-0000-0000-0000-000000000001", [(
                "UPDATE users SET mfa_secret = 'JBSWY3DPEHPK3PXP', mfa_enabled = false WHERE id = CAST(:i AS uuid)",
                {"i": member["id"]})]))
        assert "access_token" in login(member["email"], PASSWORD).json()
        assert "access_token" in login(member["email"], PASSWORD).json()  # read again, after resealing


class TestAdminReset:
    def test_admin_resets_a_teammate(self, client, login, sarah, member):
        enroll(client, member)
        reset = client.post(f"/api/v1/org/members/{member['id']}/mfa/reset", headers=bearer(sarah["access_token"]))
        assert reset.status_code == 200, reset.text
        assert "access_token" in login(member["email"], PASSWORD).json()

    def test_another_organizations_admin_cannot(self, client, login, lisa, member):
        enroll(client, member)
        reset = client.post(f"/api/v1/org/members/{member['id']}/mfa/reset", headers=bearer(lisa["access_token"]))
        assert reset.status_code == 404
        assert login(member["email"], PASSWORD).json().get("mfa_required") is True

    def test_non_admins_and_self_reset_are_refused(self, client, sarah, member):
        assert client.post(f"/api/v1/org/members/{member['id']}/mfa/reset", headers=member["h"]).status_code == 403
        sarah_id = jwt.decode(sarah["access_token"], options={"verify_signature": False})["sub"]
        assert client.post(f"/api/v1/org/members/{sarah_id}/mfa/reset",
                           headers=bearer(sarah["access_token"])).status_code == 400


def test_accepting_an_invitation_records_the_sign_in(client, sarah, member):
    members = client.get("/api/v1/org/members", headers=bearer(sarah["access_token"])).json()["members"]
    joined = next(m for m in members if m["email"] == member["email"])
    assert joined["last_login_at"]
