"""
Password change and reset actually change the password, reset links work once and expire,
answers do not reveal which accounts exist, and other sessions are signed out.
Runs on both backends, like the rest of the security suite.
"""

import asyncio
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from libs.integrations import reports


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member(client, sarah):
    email = f"pw-{uuid.uuid4().hex[:8]}@example.com"
    invited = client.post("/api/v1/org/invitations", json={"email": email, "roles": ["analyst"]},
                          headers=bearer(sarah["access_token"]))
    token = invited.json()["invite_url"].split("#", 1)[1]
    tokens = client.post("/api/v1/invitations/accept", json={"token": token, "name": "P", "password": "first-password"}).json()
    return {"email": email, "tokens": tokens}


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setenv("SMTP_HOST", "mail.example.com")
    monkeypatch.setattr(reports, "_send_sync", lambda config, to, subject, text, html: sent.append(
        {"to": to, "subject": subject, "text": text}))
    return sent


def wait_for(outbox, n, timeout=5.0):
    end = time.time() + timeout
    while len(outbox) < n and time.time() < end:
        time.sleep(0.05)
    return outbox


class TestChange:
    def test_change_password_really_changes_it_and_signs_out_other_sessions(self, client, login, member):
        old_refresh = member["tokens"]["refresh_token"]
        time.sleep(1.1)  # token times are in whole seconds
        changed = client.post("/api/v1/auth/change-password", headers=bearer(member["tokens"]["access_token"]),
                              json={"current_password": "first-password", "new_password": "second-password"})
        assert changed.status_code == 200, changed.text
        assert "access_token" in changed.json() and "refresh_token" in changed.json()
        assert login(member["email"], "first-password").status_code == 401
        assert login(member["email"], "second-password").status_code == 200
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": changed.json()["refresh_token"]}).status_code == 200

    @pytest.mark.parametrize("body", [{"current_password": "wrong-password", "new_password": "second-password"},
                                      {"current_password": "first-password", "new_password": "first-password"},
                                      {"current_password": "first-password", "new_password": "short"}])
    def test_wrong_current_same_or_short_is_refused(self, client, login, member, body):
        assert client.post("/api/v1/auth/change-password", headers=bearer(member["tokens"]["access_token"]),
                           json=body).status_code == 400
        assert login(member["email"], "first-password").status_code == 200

    def test_demo_accounts_cannot(self, client, sarah):
        assert client.post("/api/v1/auth/change-password", headers=bearer(sarah["access_token"]),
                           json={"current_password": "x", "new_password": "whatever-123"}).status_code == 400


class TestReset:
    def test_without_email_it_says_so(self, client, monkeypatch):
        monkeypatch.delenv("SMTP_HOST", raising=False)
        assert client.post("/api/v1/auth/forgot-password", json={"email": "anyone@example.com"}).status_code == 503

    def test_the_answer_does_not_reveal_accounts(self, client, member, outbox):
        known = client.post("/api/v1/auth/forgot-password", json={"email": member["email"]})
        unknown = client.post("/api/v1/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.com"})
        assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
        mails = wait_for(outbox, 1)
        assert [m["to"] for m in mails] == [[member["email"]]]

    def test_a_reset_link_works_once_and_signs_out_other_sessions(self, client, login, member, outbox):
        time.sleep(1.1)
        client.post("/api/v1/auth/forgot-password", json={"email": member["email"]})
        token = re.search(r"/reset-password#([\w-]+)", wait_for(outbox, 1)[-1]["text"]).group(1)
        done = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "reset-password-1"})
        assert done.status_code == 200, done.text
        assert login(member["email"], "reset-password-1").status_code == 200
        assert login(member["email"], "first-password").status_code == 401
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": member["tokens"]["refresh_token"]}).status_code == 401
        again = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "reset-password-2"})
        assert again.status_code == 400

    def test_a_newer_request_invalidates_the_older_link(self, client, member, outbox):
        client.post("/api/v1/auth/forgot-password", json={"email": member["email"]})
        first = re.search(r"#([\w-]+)", wait_for(outbox, 1)[-1]["text"]).group(1)
        client.post("/api/v1/auth/forgot-password", json={"email": member["email"]})
        second = re.search(r"#([\w-]+)", wait_for(outbox, 2)[-1]["text"]).group(1)
        assert client.post("/api/v1/auth/reset-password", json={"token": first, "new_password": "x-password-1"}).status_code == 400
        assert client.post("/api/v1/auth/reset-password", json={"token": second, "new_password": "x-password-2"}).status_code == 200

    def test_an_expired_link_is_refused(self, client, apps, member):
        import hashlib
        token = "expired-" + uuid.uuid4().hex
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        asyncio.run(apps["gateway"].audit_store.request_password_reset(member["email"],
                                                                        hashlib.sha256(token.encode()).hexdigest(), past))
        assert client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "late-password"}).status_code == 400
