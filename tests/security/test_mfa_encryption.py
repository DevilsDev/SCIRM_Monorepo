"""
MFA (TOTP) seeds are encrypted at rest with AES-256-GCM, bound to the user. Runs on both
backends, like the rest of the security suite.
"""

import asyncio
import base64
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from libs.common import secret_box
from libs.common.auth import generate_totp

ROOT = Path(__file__).resolve().parents[2]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def raw_secret(apps, user_id):
    """The value as stored, bypassing decryption."""
    store = apps["gateway"].audit_store
    if hasattr(store, "users"):
        return store.users[str(user_id)]["mfa_secret"]
    rows = asyncio.run(store._all(None, "SELECT mfa_secret FROM scirm_user_by_id(CAST(:i AS uuid))", {"i": str(user_id)}))
    return rows[0]["mfa_secret"]


@pytest.fixture
def member(client, sarah):
    """A stored (non-demo) account in org 1."""
    email = f"mfa-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post("/api/v1/org/invitations", json={"email": email, "roles": ["analyst"]},
                          headers=bearer(sarah["access_token"]))
    token = invited.json()["invite_url"].split("#", 1)[1]
    tokens = client.post("/api/v1/invitations/accept", json={"token": token, "name": "M", "password": "a-good-password"}).json()
    return {"email": email, "tokens": tokens, "id": __import__("jwt").decode(tokens["access_token"],
                                                                            options={"verify_signature": False})["sub"]}


class TestBox:
    def test_round_trip_and_binding_to_the_user(self, monkeypatch):
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", key())
        sealed = secret_box.encrypt("JBSWY3DPEHPK3PXP", "user-1")
        assert sealed.startswith("enc:v1:") and "JBSWY3DPEHPK3PXP" not in sealed
        assert secret_box.encrypt("JBSWY3DPEHPK3PXP", "user-1") != sealed  # random nonce
        assert secret_box.decrypt(sealed, "user-1") == ("JBSWY3DPEHPK3PXP", False)
        with pytest.raises(secret_box.SecretBoxError):
            secret_box.decrypt(sealed, "user-2")  # copied onto another account

    def test_rotation_reads_old_values_and_flags_them(self, monkeypatch):
        old, new = key(), key()
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", old)
        sealed = secret_box.encrypt("SEED", "u")
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", new)
        with pytest.raises(secret_box.SecretBoxError):
            secret_box.decrypt(sealed, "u")
        monkeypatch.setenv("MFA_ENCRYPTION_KEY_PREVIOUS", old)
        assert secret_box.decrypt(sealed, "u") == ("SEED", True)

    def test_legacy_plaintext_is_readable_and_flagged(self):
        assert secret_box.decrypt("JBSWY3DPEHPK3PXP", "u") == ("JBSWY3DPEHPK3PXP", True)

    @pytest.mark.parametrize("bad", ["short", base64.urlsafe_b64encode(b"x" * 16).decode()])
    def test_bad_keys_are_refused(self, monkeypatch, bad):
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", bad)
        with pytest.raises(secret_box.SecretBoxError):
            secret_box.require_key()


class TestStoredAccounts:
    def test_setup_stores_ciphertext_and_sign_in_works(self, client, login, apps, member):
        setup = client.post("/api/v1/auth/mfa/setup", headers=bearer(member["tokens"]["access_token"])).json()
        stored = raw_secret(apps, member["id"])
        assert stored.startswith("enc:v1:") and setup["secret"] not in stored
        assert client.post("/api/v1/auth/mfa/confirm", json={"totp_code": generate_totp(setup["secret"])},
                           headers=bearer(member["tokens"]["access_token"])).status_code == 200
        challenge = login(member["email"], "a-good-password").json()
        assert challenge.get("mfa_required") is True, challenge
        verified = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"],
                                                               "totp_code": generate_totp(setup["secret"])})
        assert verified.status_code == 200, verified.text

    def test_a_legacy_plaintext_seed_is_encrypted_when_read(self, client, login, apps, member):
        store = apps["gateway"].audit_store
        seed = "JBSWY3DPEHPK3PXP"
        if hasattr(store, "users"):
            store.users[str(member["id"])].update(mfa_secret=seed, mfa_enabled=True)
        else:
            asyncio.run(store._exec("a0000000-0000-0000-0000-000000000001", [(
                "UPDATE users SET mfa_secret = :s, mfa_enabled = true WHERE id = CAST(:i AS uuid)",
                {"s": seed, "i": member["id"]})]))
        challenge = login(member["email"], "a-good-password").json()  # reads the account
        assert challenge.get("mfa_required") is True
        assert raw_secret(apps, member["id"]).startswith("enc:v1:")
        verified = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"],
                                                               "totp_code": generate_totp(seed)})
        assert verified.status_code == 200, verified.text


def test_gateway_refuses_to_start_without_a_key_outside_development():
    code = (f"import sys, importlib.util; sys.path.insert(0, r'{ROOT}');"
            f"s = importlib.util.spec_from_file_location('gw', r'{ROOT / 'apps/api-gateway/main.py'}');"
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)")
    env = {k: v for k, v in os.environ.items() if k not in ("DEV_PASSWORD", "MFA_ENCRYPTION_KEY")}
    env.update({"ENVIRONMENT": "production", "JWT_SECRET_KEY": "k" * 40, "SERVICE_API_KEY": "svc-key",
                "STORE_BACKEND": "postgres", "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/unused"})
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode != 0 and "MFA_ENCRYPTION_KEY" in result.stderr
    env["MFA_ENCRYPTION_KEY"] = key()
    ok = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert ok.returncode == 0, ok.stderr
