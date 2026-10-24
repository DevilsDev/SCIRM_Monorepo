"""
Regulatory watch: an organization's watchlist of substances and products, the FDA and EMA
records that name them, the watchlist.matched webhook event and the digest section. The
watchlist is tenant data; the records are public. Runs on both backends.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from libs.common.auth import TOKEN_TYPE_ACCESS, decode_token
from libs.evidence import answer, verify
from libs.integrations import reports, webhooks


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def org_of(tokens) -> str:
    return decode_token(tokens["access_token"], TOKEN_TYPE_ACCESS)["org_id"]


def ema_dhpc(substance: str, **extra) -> dict:
    tag = uuid.uuid4().hex[:6]
    return {"source": "ema_dhpc", "external_id": f"dhpc-{tag}", "signal_type": "safety_communication",
            "title": f"EMA safety communication: Zelvaro {tag}",
            "summary": f"Direct healthcare professional communication about Zelvaro ({substance}): quality defect.",
            "severity": "high", "entity_names": [], "entity_keys": [], "country_codes": [],
            "published_at": datetime.now(timezone.utc).date().isoformat(), "updated_at": None,
            "url": f"https://www.ema.europa.eu/en/medicines/dhpc/zelvaro-{tag}",
            "raw": {"medicine": f"Zelvaro {tag}", "substances": [substance], "kinds": ["Quality defect"]}, **extra}


def fda_recall(product: str) -> dict:
    tag = uuid.uuid4().hex[:6]
    return {"source": "fda_recalls", "external_id": f"D-{tag}", "signal_type": "recall",
            "title": f"Class II recall: {product}", "summary": "Failed dissolution specifications.",
            "severity": "high", "entity_names": ["Some Pharma Inc."], "entity_keys": ["some pharma"], "country_codes": ["US"],
            "published_at": datetime.now(timezone.utc).date().isoformat(), "updated_at": None, "url": "https://example.test/r",
            "raw": {"classification": "Class II", "recalling_firm": "Some Pharma Inc.", "event_id": f"E-{tag}"}}


class TestWatchlist:
    def test_add_list_remove_and_duplicates(self, client, new_team):
        team = new_team(("admin", "viewer"))
        admin, viewer = bearer(team["admin"]["access_token"]), bearer(team["viewer"]["access_token"])
        added = client.post("/api/v1/watchlist", json={"kind": "substance", "term": " Zelvarocin ", "note": "API from Hikari"},
                            headers=admin)
        assert added.status_code == 200, added.text
        assert added.json()["item"]["term"] == "Zelvarocin"
        assert client.post("/api/v1/watchlist", json={"term": "ZELVAROCIN"}, headers=admin).status_code == 409
        assert client.post("/api/v1/watchlist", json={"term": "ab"}, headers=admin).status_code == 422
        assert client.post("/api/v1/watchlist", json={"term": "Other"}, headers=viewer).status_code == 403
        assert [i["term"] for i in client.get("/api/v1/watchlist", headers=viewer).json()["items"]] == ["Zelvarocin"]
        item = added.json()["item"]["id"]
        assert client.delete(f"/api/v1/watchlist/{item}", headers=viewer).status_code == 403
        assert client.delete(f"/api/v1/watchlist/{item}", headers=admin).status_code == 200
        assert client.get("/api/v1/watchlist", headers=admin).json()["items"] == []
        log = client.get("/api/v1/audit", params={"limit": 50}, headers=admin).json()["entries"]
        assert {"watchlist.added", "watchlist.removed"} <= {e["action"] for e in log}

    def test_watchlists_stay_in_their_organization(self, client, new_team):
        ours, theirs = new_team(("admin",))["admin"], new_team(("admin",))["admin"]
        item = client.post("/api/v1/watchlist", json={"term": "Quorvastatin"}, headers=bearer(ours["access_token"])).json()["item"]
        assert client.get("/api/v1/watchlist", headers=bearer(theirs["access_token"])).json()["items"] == []
        assert client.delete(f"/api/v1/watchlist/{item['id']}", headers=bearer(theirs["access_token"])).status_code == 404


class TestMatches:
    def test_fda_and_ema_records_that_name_a_watched_term(self, client, apps, new_team):
        team = new_team(("admin",))
        admin = bearer(team["admin"]["access_token"])
        substance = f"vorlaxitinib{uuid.uuid4().hex[:4]}"
        asyncio.run(apps["gateway"].audit_store.upsert_signals([
            ema_dhpc(substance), fda_recall(f"{substance.upper()} Tablets, 20 mg"), ema_dhpc("unrelated substance"),
            {**fda_recall("x"), "source": "gdacs", "signal_type": "disaster", "title": f"Flood near {substance} plant",
             "country_codes": [], "entity_keys": []}]))
        assert client.get("/api/v1/regulatory-watch", headers=admin).json()["matches"] == []  # nothing watched yet
        client.post("/api/v1/watchlist", json={"term": substance}, headers=admin)
        found = client.get("/api/v1/regulatory-watch", headers=admin).json()
        assert sorted(m["record"]["source"] for m in found["matches"]) == ["ema_dhpc", "fda_recalls"]  # not GDACS
        assert all(m["terms"] == [substance] for m in found["matches"])
        only_ema = client.get("/api/v1/regulatory-watch", params={"source": "ema_dhpc"}, headers=admin).json()
        assert [m["record"]["source"] for m in only_ema["matches"]] == ["ema_dhpc"]
        assert client.get("/api/v1/regulatory-watch", params={"source": "gdacs"}, headers=admin).status_code == 400
        other = bearer(new_team(("admin",))["admin"]["access_token"])
        assert client.get("/api/v1/regulatory-watch", headers=other).json()["matches"] == []


class TestDelivery:
    def test_new_matching_records_become_watchlist_events_once(self, apps):
        store = apps["gateway"].audit_store
        substance = f"brenoxatide{uuid.uuid4().hex[:4]}"

        async def scenario():
            org = await store.create_organization(f"Watch org {uuid.uuid4().hex[:6]}")
            await store.add_watchlist_item(org, "substance", substance, "", "t")
            await store.upsert_signals([ema_dhpc(substance)])  # before webhooks existed: not replayed
            await webhooks.detect(store, org)  # sets the watermark
            await asyncio.sleep(0.01)
            await store.upsert_signals([ema_dhpc(substance), ema_dhpc("something else")])
            first = await webhooks.detect(store, org)
            second = await webhooks.detect(store, org)  # the overlap window re-reads: deduplicated
            now = datetime.now(timezone.utc)
            events = await store.list_events(org, (now - timedelta(hours=1)).isoformat(), (now + timedelta(minutes=1)).isoformat())
            return first, second, events
        first, second, events = asyncio.run(scenario())
        assert (first, second) == (1, 0)
        [event] = events
        assert event["type"] == "watchlist.matched" and event["payload"]["terms"] == [substance]
        assert event["payload"]["record"]["source"] == "ema_dhpc"

    def test_the_digest_lists_watchlist_matches(self):
        event = {"type": "watchlist.matched", "payload": {"terms": ["rifampicin"], "record": {
            "title": "EMA referral: Rifadin oral suspension", "source": "ema_referrals", "severity": "medium",
            "url": "https://www.ema.europa.eu/x", "published_at": "2026-06-26"}}}
        now = datetime.now(timezone.utc)
        subject, text, html = reports.build_digest("Acme", [event], now - timedelta(days=7), now)
        assert "1 regulatory watch match(es)" in subject
        assert "Regulatory watch" in text and "Watching rifampicin: EMA referral: Rifadin oral suspension" in text
        assert "Watching rifampicin" in html


class TestEvidence:
    def test_ema_sentences_pass_the_citation_checker(self):
        for record in (
            {"signal_type": "ema_shortage", "published_at": "2024-06-03", "title": "EMA medicine shortage: Natpar",
             "summary": "Medicine discontinued. Active substance: parathyroid hormone.",
             "raw": {"medicine": "Natpar", "substances": ["parathyroid hormone"], "status": "discontinued"}},
            {"signal_type": "safety_communication", "published_at": "2026-08-20", "title": "EMA safety communication: Jentadueto",
             "summary": "Direct healthcare professional communication about Jentadueto (linagliptin): quality defect.",
             "raw": {"medicine": "Jentadueto", "substances": ["linagliptin"]}},
            {"signal_type": "referral", "published_at": "2026-06-26", "title": "EMA referral: Rifadin oral suspension",
             "summary": "Referral (Article 31 referrals): Procedure started. Active substance: rifampicin.",
             "raw": {"medicine": "Rifadin oral suspension", "substances": ["rifampicin"], "status": "Procedure started",
                     "safety": False}},
        ):
            text = answer.describe(record)
            assert verify.check_claim(f"{text} [S1]", ["S1"], {"S1": record}) == [], text
