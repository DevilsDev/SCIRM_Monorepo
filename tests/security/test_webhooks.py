"""
Webhooks: admin-only endpoints, signed deliveries, retries, the outbound address guard,
and detection of new public records matching a tenant's suppliers (deduplicated, never
replaying the archive). Runs on both backends, like the rest of the security suite.
"""

import asyncio
import json
import uuid

import httpx
import pytest

from libs.integrations import webhooks

ORG_1 = "a0000000-0000-0000-0000-000000000001"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class Receiver:
    """A fake endpoint: records requests and answers with the status set in .status."""

    def __init__(self):
        self.requests, self.status = [], 200

    def transport(self):
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            headers = {"Location": "http://169.254.169.254/"} if self.status in (301, 302) else {}
            return httpx.Response(self.status, headers=headers, text="receiver body that must not be stored")
        return httpx.MockTransport(handle)


@pytest.fixture
def receiver(monkeypatch):
    r = Receiver()
    monkeypatch.setattr(webhooks, "transport_factory", r.transport)
    return r


@pytest.fixture
def hook(client, sarah):
    created = client.post("/api/v1/org/webhooks", json={"url": "https://hooks.example.com/scirm", "description": "test"},
                          headers=bearer(sarah["access_token"]))
    assert created.status_code == 200, created.text
    body = created.json()
    yield body
    client.delete(f"/api/v1/org/webhooks/{body['webhook']['id']}", headers=bearer(sarah["access_token"]))


class TestManagement:
    def test_only_admins(self, client, auditor):
        assert client.post("/api/v1/org/webhooks", json={"url": "https://x.example.com"},
                           headers=bearer(auditor["access_token"])).status_code == 403

    def test_secret_shown_once_and_never_listed(self, client, sarah, hook):
        assert hook["secret"].startswith("whsec_")
        listed = client.get("/api/v1/org/webhooks", headers=bearer(sarah["access_token"])).json()["webhooks"]
        assert any(w["id"] == hook["webhook"]["id"] for w in listed)
        assert hook["secret"] not in json.dumps(listed) and "secret_enc" not in json.dumps(listed)

    @pytest.mark.parametrize("url", ["ftp://x.example.com", "https://user:pw@x.example.com/", "https://x.example.com/#f"])
    def test_bad_urls_are_refused(self, client, sarah, url):
        assert client.post("/api/v1/org/webhooks", json={"url": url},
                           headers=bearer(sarah["access_token"])).status_code == 400

    def test_unknown_events_are_refused(self, client, sarah):
        assert client.post("/api/v1/org/webhooks", json={"url": "https://x.example.com", "events": ["everything"]},
                           headers=bearer(sarah["access_token"])).status_code == 400

    def test_another_organization_cannot_touch_it(self, client, lisa, hook):
        hid = hook["webhook"]["id"]
        h = bearer(lisa["access_token"])
        assert client.post(f"/api/v1/org/webhooks/{hid}/test", headers=h).status_code == 404
        assert client.patch(f"/api/v1/org/webhooks/{hid}", json={"active": False}, headers=h).status_code == 404
        assert client.delete(f"/api/v1/org/webhooks/{hid}", headers=h).status_code == 404


class TestDelivery:
    def test_a_signed_ping_is_delivered(self, client, sarah, hook, receiver):
        result = client.post(f"/api/v1/org/webhooks/{hook['webhook']['id']}/test", headers=bearer(sarah["access_token"]))
        assert result.status_code == 200 and result.json()["ok"] is True, result.text
        sent = receiver.requests[-1]
        assert sent.method == "POST" and sent.headers["SCIRM-Event-Type"] == "ping"
        assert webhooks.verify(hook["secret"], sent.headers["SCIRM-Signature"], sent.content)
        assert not webhooks.verify("whsec_wrong", sent.headers["SCIRM-Signature"], sent.content)
        body = json.loads(sent.content)
        assert body["id"] == sent.headers["SCIRM-Event-Id"] and body["data"]["message"]
        log = client.get(f"/api/v1/org/webhooks/{hook['webhook']['id']}/deliveries",
                         headers=bearer(sarah["access_token"])).json()["deliveries"]
        assert log[0]["status"] == "delivered" and log[0]["type"] == "ping"

    @pytest.mark.parametrize("status", [500, 302])
    def test_failures_and_redirects_are_retried_not_followed(self, client, sarah, hook, receiver, status):
        receiver.status = status
        result = client.post(f"/api/v1/org/webhooks/{hook['webhook']['id']}/test",
                             headers=bearer(sarah["access_token"])).json()
        assert result["ok"] is False and result["status_code"] == status
        assert len(receiver.requests) == 1  # the redirect target was never requested
        log = client.get(f"/api/v1/org/webhooks/{hook['webhook']['id']}/deliveries",
                         headers=bearer(sarah["access_token"])).json()["deliveries"]
        assert log[0]["status"] == "pending" and log[0]["attempts"] == 1 and "receiver body" not in json.dumps(log)

    def test_a_paused_webhook_gets_nothing(self, client, sarah, hook, receiver):
        hid = hook["webhook"]["id"]
        client.patch(f"/api/v1/org/webhooks/{hid}", json={"active": False}, headers=bearer(sarah["access_token"]))
        assert client.post(f"/api/v1/org/webhooks/{hid}/test", headers=bearer(sarah["access_token"])).status_code == 409
        assert receiver.requests == []


def test_backoff_gives_up_after_the_last_step():
    from datetime import datetime, timezone
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert (webhooks.next_attempt(1, now) - now).total_seconds() == webhooks.BACKOFF[0]
    assert webhooks.next_attempt(len(webhooks.BACKOFF) + 1, now) is None


class TestOutboundGuard:
    def test_strict_mode_refuses_http_and_private_addresses(self, monkeypatch, receiver):
        event = {"id": str(uuid.uuid4()), "type": "ping", "created_at": "2026-01-01T00:00:00+00:00", "payload": {}}
        plain = asyncio.run(webhooks.deliver("http://hooks.example.com/", "s", event, strict=True))
        assert plain["ok"] is False and "https" in plain["error"]
        for ip in ("10.0.0.5", "169.254.169.254", "127.0.0.1"):
            monkeypatch.setattr(webhooks, "resolve", lambda host, port, ip=ip: [ip])
            result = asyncio.run(webhooks.deliver("https://hooks.example.com/", "s", event, strict=True))
            assert result["ok"] is False and "public" in result["error"]
        assert receiver.requests == []

    def test_strict_mode_sends_to_the_checked_address_with_the_original_name(self, monkeypatch, receiver):
        monkeypatch.setattr(webhooks, "resolve", lambda host, port: ["93.184.216.34"])
        event = {"id": str(uuid.uuid4()), "type": "ping", "created_at": "2026-01-01T00:00:00+00:00", "payload": {}}
        assert asyncio.run(webhooks.deliver("https://hooks.example.com/in?x=1", "s", event, strict=True))["ok"]
        sent = receiver.requests[-1]
        assert sent.url.host == "93.184.216.34" and sent.headers["Host"] == "hooks.example.com"
        assert sent.url.query == b"x=1"


class TestDetection:
    """On one store: a tenant, its supplier, an endpoint, then new public records."""

    def _signal(self, **extra):
        base = {"source": "fda_recalls", "external_id": f"wh-{uuid.uuid4().hex[:8]}", "signal_type": "recall",
                "title": "Recall: Zentrix tablets", "summary": "", "severity": "high",
                "entity_names": ["Zentrix Pharma Inc."], "entity_keys": ["zentrix"], "country_codes": ["US"],
                "published_at": "2026-10-01", "updated_at": None, "raw": {"event_id": "E-1"}}
        return {**base, **extra}

    def test_new_records_become_one_event_per_recall_event_and_supplier(self, apps, receiver):
        store = apps["gateway"].audit_store

        async def scenario():
            org = await store.create_organization(f"Webhook org {uuid.uuid4().hex[:6]}")
            await store.create_supplier(org, {"name": "Zentrix Pharma Inc.", "supplier_code": "ZX-1",
                                              "supplier_type": "manufacturer", "country_code": "US"})
            old = self._signal(external_id=f"old-{uuid.uuid4().hex[:6]}", raw={"event_id": "OLD"})
            await store.upsert_signals([old])
            secret = webhooks.new_secret()
            hook = await store.create_webhook(org, "https://hooks.example.com/a", None, ["record.matched"], secret, "t")
            exposure_only = await store.create_webhook(org, "https://hooks.example.com/b", None,
                                                       ["exposure.detected"], webhooks.new_secret(), "t")
            first = await webhooks.detect(store, org)  # sets the watermark only: the archive is not replayed
            await asyncio.sleep(0.01)
            await store.upsert_signals([self._signal(), self._signal()])  # two records of recall event E-1
            second = await webhooks.detect(store, org)
            third = await webhooks.detect(store, org)  # nothing new
            sent = await webhooks.deliver_due(store, org)
            return first, second, third, sent, hook, exposure_only, secret

        first, second, third, sent, hook, exposure_only, secret = asyncio.run(scenario())
        assert (first, second, third) == (0, 1, 0)
        assert [s["webhook_id"] for s in sent] == [hook["id"]] and sent[0]["ok"]
        body = json.loads(receiver.requests[-1].content)
        assert body["type"] == "record.matched" and body["data"]["record_count"] == 2
        assert body["data"]["supplier"]["name"] == "Zentrix Pharma Inc."
        assert body["data"]["event_key"] == "fda_recalls:event:E-1"
        assert webhooks.verify(secret, receiver.requests[-1].headers["SCIRM-Signature"], receiver.requests[-1].content)

    def test_events_are_inserted_once_even_when_recorded_twice(self, apps):
        store = apps["gateway"].audit_store

        async def scenario():
            org = await store.create_organization(f"Dedupe org {uuid.uuid4().hex[:6]}")
            await store.create_webhook(org, "https://hooks.example.com/c", None, ["record.matched"],
                                       webhooks.new_secret(), "t")
            event = ("record.matched", "record.matched:s1:k1", {"x": 1})
            return (await store.record_events(org, [event]), await store.record_events(org, [event]),
                    await store.claim_deliveries(org), await store.claim_deliveries(org))

        once, twice, claimed, again = asyncio.run(scenario())
        assert len(once) == 1 and twice == []
        assert len(claimed) == 1 and again == []  # leased: a second worker gets nothing
