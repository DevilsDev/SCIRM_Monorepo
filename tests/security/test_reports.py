"""
Scheduled reports: schedule arithmetic, the digest's content and escaping, admin-only API
with recipients limited to members, and the runner (lease, member re-check, skip empty).
Runs on both backends, like the rest of the security suite.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from libs.integrations import reports


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class TestNextRun:
    def test_daily(self):
        assert reports.next_run("daily", 7, None, at("2026-10-23T06:59:00")) == at("2026-10-23T07:00:00")
        assert reports.next_run("daily", 7, None, at("2026-10-23T07:00:00")) == at("2026-10-24T07:00:00")

    def test_weekly(self):  # 2026-10-23 is a Friday (weekday 4)
        assert reports.next_run("weekly", 8, 0, at("2026-10-23T10:00:00")) == at("2026-10-26T08:00:00")
        assert reports.next_run("weekly", 8, 4, at("2026-10-23T07:00:00")) == at("2026-10-23T08:00:00")
        assert reports.next_run("weekly", 8, 4, at("2026-10-23T09:00:00")) == at("2026-10-30T08:00:00")

    def test_monthly_rolls_over_the_year(self):
        assert reports.next_run("monthly", 6, None, at("2026-12-01T06:00:00")) == at("2027-01-01T06:00:00")
        assert reports.next_run("monthly", 6, None, at("2026-11-30T23:00:00")) == at("2026-12-01T06:00:00")


def _event(etype="record.matched", supplier="Zentrix Pharma", title="Recall: tablets", **extra):
    payload = {"supplier": {"name": supplier}, "match": {"match_type": "name_exact"},
               "record": {"title": title, "url": "https://www.fda.gov/x", "severity": "high",
                          "published_at": "2026-10-20", "source": "fda_recalls"}, "record_count": 1, **extra}
    return {"id": str(uuid.uuid4()), "type": etype, "payload": payload, "created_at": "2026-10-22T00:00:00+00:00"}


class TestDigest:
    def test_counts_and_content(self):
        subject, text, body = reports.build_digest("Acme", [_event(), _event("exposure.detected", "Osaka KK", "Earthquake",
                                                                             match={"site": {"site": "Plant 2", "distance_km": 14}})],
                                                   at("2026-10-16T00:00:00"), at("2026-10-23T00:00:00"), "https://scirm.example")
        assert "1 new record" in subject and "1 disaster exposure" in subject
        assert "Zentrix Pharma" in text and "14 km from Plant 2" in text and "https://scirm.example/suppliers" in body

    def test_untrusted_text_is_escaped(self):
        _, _, body = reports.build_digest("<b>Org</b>", [_event(supplier="<script>x</script>", title="a\"><img src=x>")],
                                          at("2026-10-16T00:00:00"), at("2026-10-23T00:00:00"))
        assert "<script>" not in body and "<img" not in body and "&lt;script&gt;" in body and "<b>Org" not in body

    def test_an_empty_period_says_so(self):
        subject, text, _ = reports.build_digest("Acme", [], at("2026-10-16T00:00:00"), at("2026-10-23T00:00:00"))
        assert "nothing new" in subject and "No new public records" in text


class TestApi:
    def _create(self, client, token, **overrides):
        body = {"name": "Weekly digest", "frequency": "weekly", "weekday": 0, "hour_utc": 7,
                "recipients": ["sarah.chen@pharmacorp.com"], **overrides}
        return client.post("/api/v1/org/reports", json=body, headers=bearer(token))

    def test_admins_create_and_list(self, client, sarah):
        created = self._create(client, sarah["access_token"])
        assert created.status_code == 200, created.text
        schedule = created.json()["schedule"]
        assert schedule["when"] == "Every Monday at 07:00 UTC" and schedule["next_run_at"]
        listed = client.get("/api/v1/org/reports", headers=bearer(sarah["access_token"])).json()
        assert any(s["id"] == schedule["id"] for s in listed["schedules"]) and "email_configured" in listed

    def test_only_admins(self, client, auditor):
        assert self._create(client, auditor["access_token"]).status_code == 403

    def test_recipients_must_be_members(self, client, sarah):
        refused = self._create(client, sarah["access_token"], recipients=["someone@gmail.com"])
        assert refused.status_code == 400 and "someone@gmail.com" in refused.json()["detail"]
        assert self._create(client, sarah["access_token"], recipients=["lisa.park@medtech.com"]).status_code == 400

    @pytest.mark.parametrize("bad", [{"frequency": "hourly"}, {"frequency": "weekly", "weekday": None}, {"hour_utc": 24}])
    def test_bad_timing_is_refused(self, client, sarah, bad):
        assert self._create(client, sarah["access_token"], **bad).status_code in (400, 422)

    def test_another_organization_cannot_touch_it(self, client, sarah, lisa):
        sid = self._create(client, sarah["access_token"]).json()["schedule"]["id"]
        h = bearer(lisa["access_token"])
        assert client.patch(f"/api/v1/org/reports/{sid}", json={"active": False}, headers=h).status_code == 404
        assert client.delete(f"/api/v1/org/reports/{sid}", headers=h).status_code == 404

    def test_send_now_needs_email_configured(self, client, sarah, monkeypatch):
        sid = self._create(client, sarah["access_token"]).json()["schedule"]["id"]
        monkeypatch.delenv("SMTP_HOST", raising=False)
        assert client.post(f"/api/v1/org/reports/{sid}/send-now", headers=bearer(sarah["access_token"])).status_code == 409
        monkeypatch.setenv("SMTP_HOST", "mail.example.com")
        queued = client.post(f"/api/v1/org/reports/{sid}/send-now", headers=bearer(sarah["access_token"]))
        assert queued.status_code == 200
        assert datetime.fromisoformat(queued.json()["schedule"]["next_run_at"]) <= datetime.now(timezone.utc)


class TestRunner:
    @pytest.fixture
    def outbox(self, monkeypatch):
        sent = []
        monkeypatch.setenv("SMTP_HOST", "mail.example.com")
        monkeypatch.setattr(reports, "_send_sync", lambda config, to, subject, text, html: sent.append(
            {"to": to, "subject": subject, "text": text, "html": html}))
        return sent

    def test_a_due_report_is_sent_once_to_members_with_the_period_events(self, apps, outbox):
        store = apps["gateway"].audit_store

        async def scenario():
            org = await store.create_organization(f"Report org {uuid.uuid4().hex[:6]}")
            member = f"risk-{uuid.uuid4().hex[:6]}@example.com"
            await store.create_user(org, member, "Risk lead", "x", ["analyst"])
            await store.record_events(org, [("record.matched", f"k-{uuid.uuid4()}", _event(supplier="Quorvane Labs")["payload"])])
            due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            await store.create_report_schedule(org, {"name": "Daily", "frequency": "daily", "hour_utc": 6,
                                                     "recipients": [member], "next_run_at": due}, "t")
            first = await reports.run_due(store, org)
            second = await reports.run_due(store, org)  # moved to its next run: nothing due
            schedules = await store.list_report_schedules(org)
            return member, first, second, schedules

        member, first, second, schedules = asyncio.run(scenario())
        assert [r["sent"] for r in first] == [True] and second == []
        assert outbox[-1]["to"] == [member] and "Quorvane Labs" in outbox[-1]["text"]
        s = schedules[0]
        assert s["last_status"]["ok"] and s["last_run_at"]
        assert datetime.fromisoformat(s["next_run_at"]) > datetime.now(timezone.utc)

    def test_an_event_on_the_boundary_is_in_exactly_one_report(self, apps):
        """Clocks can tie (Windows ticks every ~15 ms): windows are (since, until]."""
        store = apps["gateway"].audit_store

        async def scenario():
            org = await store.create_organization(f"Edge org {uuid.uuid4().hex[:6]}")
            await store.record_events(org, [("record.matched", f"k-{uuid.uuid4()}", {"x": 1})])
            stamp = (await store.list_events(org, "2000-01-01T00:00:00+00:00", await store.db_now()))[0]["created_at"]
            before = (datetime.fromisoformat(stamp) - timedelta(days=1)).isoformat()
            later = (datetime.fromisoformat(stamp) + timedelta(days=1)).isoformat()
            return await store.list_events(org, before, stamp), await store.list_events(org, stamp, later)

        first, second = asyncio.run(scenario())
        assert len(first) == 1 and second == []

    def test_a_recipient_who_left_is_not_mailed(self, apps, outbox):
        store = apps["gateway"].audit_store

        async def scenario():
            org = await store.create_organization(f"Left org {uuid.uuid4().hex[:6]}")
            user = await store.create_user(org, f"gone-{uuid.uuid4().hex[:6]}@example.com", "Gone", "x", ["analyst"])
            await store.update_member(org, user["id"], is_active=False)
            await store.create_report_schedule(org, {"name": "D", "frequency": "daily", "hour_utc": 6,
                                                     "recipients": [user["email"]],
                                                     "next_run_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}, "t")
            return await reports.run_due(store, org)

        before = len(outbox)
        result = asyncio.run(scenario())
        assert result[0]["ok"] is False and "member" in result[0]["error"] and len(outbox) == before

    def test_skip_empty(self, apps, outbox):
        store = apps["gateway"].audit_store

        async def scenario():
            org = await store.create_organization(f"Quiet org {uuid.uuid4().hex[:6]}")
            member = f"q-{uuid.uuid4().hex[:6]}@example.com"
            await store.create_user(org, member, "Q", "x", ["analyst"])
            await store.create_report_schedule(org, {"name": "D", "frequency": "daily", "hour_utc": 6, "skip_empty": True,
                                                     "recipients": [member],
                                                     "next_run_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}, "t")
            return await reports.run_due(store, org)

        before = len(outbox)
        result = asyncio.run(scenario())
        assert result[0]["ok"] and result[0]["sent"] is False and len(outbox) == before
