"""
Tenant onboarding: invitations, team management and stored accounts. Runs on both
backends (STORE_BACKEND=memory and postgres), like the rest of the security suite.
"""

import asyncio
import uuid

import jwt as pyjwt
import pytest

from conftest import ORG_1, ORG_2, bearer


def claims(tokens):
    return pyjwt.decode(tokens["access_token"], options={"verify_signature": False})


def unique_email(prefix="person"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def invite(client, sarah):
    """Invite someone to org 1 as Sarah (admin); returns (email, token, response json)."""
    def _invite(roles=("analyst",), email=None):
        email = email or unique_email()
        response = client.post("/api/v1/org/invitations", json={"email": email, "roles": list(roles)},
                               headers=bearer(sarah["access_token"]))
        assert response.status_code == 200, response.text
        body = response.json()
        return email, body["invite_url"].split("#", 1)[1], body
    return _invite


def accept(client, token, name="New Person", password="a-good-password"):
    return client.post("/api/v1/invitations/accept", json={"token": token, "name": name, "password": password})


class TestInvitations:
    def test_invite_accept_and_sign_in_lands_in_the_inviting_org(self, client, invite, login):
        email, token, body = invite(roles=["viewer"])
        assert body["invite_url"].startswith("http://localhost:3000/invite#")  # fragment: never sent to a server
        looked_up = client.post("/api/v1/invitations/lookup", json={"token": token}).json()
        assert looked_up["email"] == email and looked_up["roles"] == ["viewer"]
        response = accept(client, token)
        assert response.status_code == 200, response.text
        assert claims(response.json())["org_id"] == ORG_1 and claims(response.json())["roles"] == ["viewer"]
        assert login(email.upper(), "a-good-password").status_code == 200  # emails are case-insensitive

    def test_a_token_works_once(self, client, invite):
        _, token, _ = invite()
        assert accept(client, token).status_code == 200
        assert accept(client, token).status_code == 404
        assert client.post("/api/v1/invitations/lookup", json={"token": token}).status_code == 404

    def test_revoked_and_expired_invitations_are_refused(self, client, invite, sarah, apps):
        _, token, body = invite()
        revoked = client.delete(f"/api/v1/org/invitations/{body['invitation']['id']}", headers=bearer(sarah["access_token"]))
        assert revoked.status_code == 200
        assert accept(client, token).status_code == 404
        store = apps["gateway"].audit_store
        _, expired = asyncio.run(store.create_invitation(ORG_1, unique_email("late"), ["analyst"], None, ttl_hours=0))
        assert client.post("/api/v1/invitations/lookup", json={"token": expired}).status_code == 404
        assert accept(client, expired).status_code == 404

    def test_inviting_an_existing_account_is_a_conflict(self, client, sarah):
        response = client.post("/api/v1/org/invitations", json={"email": "Marcus.Rodriguez@pharmacorp.com"},
                               headers=bearer(sarah["access_token"]))
        assert response.status_code == 409

    def test_only_admins_invite_and_roles_are_validated(self, client, auditor, sarah):
        assert client.post("/api/v1/org/invitations", json={"email": unique_email()},
                           headers=bearer(auditor["access_token"])).status_code == 403
        assert client.post("/api/v1/org/invitations", json={"email": unique_email(), "roles": ["superuser"]},
                           headers=bearer(sarah["access_token"])).status_code == 400

    def test_tokens_never_reach_the_audit_log(self, client, invite, sarah):
        _, token, _ = invite()
        accept(client, token)
        entries = client.get("/api/v1/audit", headers=bearer(sarah["access_token"])).json()["entries"]
        assert any(e["action"] == "invitation.accepted" for e in entries)
        assert token not in str(entries)

    def test_a_weak_password_is_refused_and_the_invitation_survives(self, client, invite):
        _, token, _ = invite()
        assert accept(client, token, password="short").status_code == 400
        assert accept(client, token).status_code == 200


class TestTenantIsolation:
    def test_another_org_cannot_see_or_revoke_invitations(self, client, invite, lisa):
        _, _, body = invite()
        theirs = client.get("/api/v1/org/invitations", headers=bearer(lisa["access_token"])).json()["invitations"]
        assert body["invitation"]["id"] not in {i["id"] for i in theirs}
        assert client.delete(f"/api/v1/org/invitations/{body['invitation']['id']}",
                             headers=bearer(lisa["access_token"])).status_code == 404

    def test_another_org_cannot_see_or_change_members(self, client, invite, lisa, sarah):
        email, token, _ = invite()
        member_id = claims(accept(client, token).json())["sub"]
        org2 = client.get("/api/v1/org/members", headers=bearer(lisa["access_token"])).json()["members"]
        assert email not in {m["email"] for m in org2}
        assert client.patch(f"/api/v1/org/members/{member_id}", json={"is_active": False},
                            headers=bearer(lisa["access_token"])).status_code == 404
        org1 = client.get("/api/v1/org/members", headers=bearer(sarah["access_token"])).json()["members"]
        listed = next(m for m in org1 if m["email"] == email)
        assert "hashed_password" not in listed and "mfa_secret" not in listed


class TestMembers:
    def test_deactivated_member_cannot_sign_in_or_refresh(self, client, invite, sarah, login):
        email, token, _ = invite()
        tokens = accept(client, token).json()
        member_id = claims(tokens)["sub"]
        assert client.patch(f"/api/v1/org/members/{member_id}", json={"is_active": False},
                            headers=bearer(sarah["access_token"])).status_code == 200
        assert login(email, "a-good-password").status_code == 401
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401

    def test_roles_can_change_but_the_last_admin_stays(self, client, login):
        # A fresh organization through sign-up (open in development): its creator is the only admin.
        email = unique_email("owner")
        tokens = client.post("/api/v1/auth/signup", json={"email": email, "password": "a-good-password", "name": "Owner",
                                                           "organization_name": "Owner Co"}).json()
        me = claims(tokens)["sub"]
        headers = bearer(tokens["access_token"])
        assert client.patch(f"/api/v1/org/members/{me}", json={"roles": ["analyst"]}, headers=headers).status_code == 409
        assert client.patch(f"/api/v1/org/members/{me}", json={"is_active": False}, headers=headers).status_code == 400
        # With a second admin, the first can step down.
        invited = client.post("/api/v1/org/invitations", json={"email": unique_email(), "roles": ["admin"]},
                              headers=headers).json()
        accept(client, invited["invite_url"].split("#", 1)[1])
        stepped_down = client.patch(f"/api/v1/org/members/{me}", json={"roles": ["analyst"]}, headers=headers)
        assert stepped_down.status_code == 200 and stepped_down.json()["roles"] == ["analyst"]

    def test_signed_up_accounts_are_stored_and_survive(self, client, login, apps):
        email = unique_email("stored")
        client.post("/api/v1/auth/signup", json={"email": email, "password": "a-good-password", "name": "S"})
        stored = asyncio.run(apps["gateway"].audit_store.find_login_user(email))
        assert stored and stored["organization_id"] not in (ORG_1, ORG_2) and stored["is_active"]
        assert login(email, "a-good-password").status_code == 200
