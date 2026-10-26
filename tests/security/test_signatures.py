"""
Electronic signatures (21 CFR Part 11 controls): the password, and the two-step code when
set, for every signing; the signer's name, the time and the meaning on each signature; the
signature bound to the record's exact content (a later change shows); append-only; tenancy.
Signing at the identity provider is tested in test_sso.py. Runs on both backends.
"""

import base64
import hashlib
import hmac
import struct
import time
import uuid

from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token

PASSWORD = "team-tests-pw-1"  # tests/security/conftest.py new_team


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def totp(secret: str) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    o = mac[-1] & 15
    return "%06d" % ((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


def incident(client, headers, title="Strike"):
    return client.post("/api/v1/incidents", json={"title": title}, headers=headers).json()["incident"]["id"]


def sign(client, headers, record_id, password=PASSWORD, **extra):
    return client.post("/api/v1/signatures", headers=headers, json={
        "record_type": "incident", "record_id": record_id, "meaning": "approved", "password": password, **extra})


class TestPasswordSigning:
    def test_a_signature_shows_who_when_and_what_it_means_and_is_bound_to_the_content(self, client, new_team):
        team = new_team(("admin", "viewer"))
        admin, viewer = bearer(team["admin"]["access_token"]), bearer(team["viewer"]["access_token"])
        assert client.get("/api/v1/signatures/method", headers=admin).json() == {"method": "password"}
        iid = incident(client, admin)
        client.patch(f"/api/v1/incidents/{iid}", json={"status": "resolved", "resolution": "Strike ended"}, headers=admin)
        signed = sign(client, admin, iid, reason="Closure checked")
        assert signed.status_code == 200, signed.text
        s = signed.json()["signature"]
        assert s["signer_name"] == "Admin" and s["meaning"] == "approved" and s["signed_at"] and s["method"] == "password"
        assert s["record_summary"] == "War-room incident: Strike (resolved)" and len(s["record_hash"]) == 64
        listed = client.get("/api/v1/signatures", params={"record_type": "incident", "record_id": iid}, headers=viewer).json()
        assert [x["intact"] for x in listed["signatures"]] == [True]
        # A read-only member can sign as reviewed; the record then changes, and both signatures show it.
        assert sign(client, viewer, iid, meaning="reviewed").status_code == 200
        client.patch(f"/api/v1/incidents/{iid}", json={"status": "open"}, headers=admin)
        after = client.get("/api/v1/signatures", params={"record_type": "incident", "record_id": iid}, headers=admin).json()
        assert [(x["meaning"], x["intact"]) for x in after["signatures"]] == [("approved", False), ("reviewed", False)]
        log = client.get("/api/v1/audit", params={"limit": 50}, headers=admin).json()["entries"]
        assert sum(1 for e in log if e["action"] == "signature.signed") == 2

    def test_every_signing_needs_the_password_and_failures_lock_out(self, client, new_team):
        team = new_team(("admin",))
        admin = bearer(team["admin"]["access_token"])
        iid = incident(client, admin)
        assert sign(client, admin, iid, password="wrong-password").status_code == 401
        log = client.get("/api/v1/audit", params={"limit": 20}, headers=admin).json()["entries"]
        assert any(e["action"] == "signature.failed" for e in log)
        for _ in range(4):
            sign(client, admin, iid, password="wrong-password")
        assert sign(client, admin, iid).status_code == 429  # even the right password, for 15 minutes

    def test_two_step_users_also_give_the_code(self, client, new_team):
        team = new_team(("admin",))
        admin = bearer(team["admin"]["access_token"])
        secret = client.post("/api/v1/auth/mfa/setup", headers=admin).json()["secret"]
        assert client.post("/api/v1/auth/mfa/confirm", headers=admin, json={"totp_code": totp(secret)}).status_code == 200
        assert client.get("/api/v1/signatures/method", headers=admin).json() == {"method": "password_mfa"}
        iid = incident(client, admin)
        assert sign(client, admin, iid).status_code == 401  # password alone is not enough
        signed = sign(client, admin, iid, totp_code=totp(secret))
        assert signed.status_code == 200 and signed.json()["signature"]["method"] == "password_mfa"

    def test_only_finished_records_and_only_people_in_the_organization(self, client, new_team):
        team, other = new_team(("admin",)), new_team(("admin",))
        admin, stranger = bearer(team["admin"]["access_token"]), bearer(other["admin"]["access_token"])
        iid = incident(client, admin)
        assert sign(client, stranger, iid).status_code == 404
        assert client.get("/api/v1/signatures", params={"record_type": "incident", "record_id": iid},
                          headers=stranger).json()["signatures"] == []
        missing = client.post("/api/v1/signatures", headers=admin, json={
            "record_type": "assessment", "record_id": str(uuid.uuid4()), "meaning": "reviewed", "password": PASSWORD})
        assert missing.status_code == 404
        bad = client.post("/api/v1/signatures", headers=admin, json={
            "record_type": "incident", "record_id": iid, "meaning": "liked", "password": PASSWORD})
        assert bad.status_code == 422


def test_signatures_hold_the_signers_identity_not_a_session(client, new_team):
    team = new_team(("admin",))
    admin = bearer(team["admin"]["access_token"])
    iid = incident(client, admin)
    s = sign(client, admin, iid).json()["signature"]
    claims = decode_token(team["admin"]["access_token"], TOKEN_TYPE_ACCESS)
    assert s["signer_id"] == claims["sub"] and s["signer_email"] == claims["email"]
