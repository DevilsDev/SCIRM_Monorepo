"""Ingestion service end to end on recorded data: ingest, feed, source status, matching."""

import importlib.util
import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("ENVIRONMENT", "test")
from intel_support import recorded_transport  # noqa: E402

ORG = "a0000000-0000-0000-0000-000000000001"
HEADERS = {"X-Org-Id": ORG}


def load_ingestion():
    previous = os.environ.get("STORE_BACKEND")
    os.environ["STORE_BACKEND"] = "memory"
    try:
        spec = importlib.util.spec_from_file_location("intel_ingestion", ROOT / "services" / "ingestion" / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            os.environ.pop("STORE_BACKEND", None)
        else:
            os.environ["STORE_BACKEND"] = previous
    return module


@pytest.fixture
def service(monkeypatch):
    module = load_ingestion()
    transport = {"value": recorded_transport()}
    monkeypatch.setattr(module, "http_client_factory", lambda: httpx.AsyncClient(transport=transport["value"]))
    # Recorded payloads have fixed dates; a long window keeps them in range whenever the tests run.
    monkeypatch.setattr(module, "LOOKBACK_DAYS", 36500)
    module.set_transport = lambda t: transport.__setitem__("value", t)
    return module


@pytest.fixture
def client(service):
    return TestClient(service.app)


def test_ingest_stores_signals_once(client):
    first = client.post("/ingest", headers=HEADERS).json()
    assert first["documents_ingested"] > 0
    assert {v["status"] for v in first["sources"].values()} == {"ok"}
    again = client.post("/ingest", headers=HEADERS).json()
    assert again["documents_ingested"] == 0, "re-ingesting must update, not duplicate"


def test_feed_keeps_its_shape_and_adds_provenance(client):
    client.post("/ingest", headers=HEADERS)
    docs = client.get("/documents", params={"since_days": 3650, "limit": 500}, headers=HEADERS).json()["documents"]
    assert docs
    for d in docs:
        assert {"id", "source", "title", "content", "severity", "region", "ingested_at"} <= set(d)
        assert d["published_at"] and d["source_label"] and d["is_demo"] is False
    activity = [d["updated_at"] or d["published_at"] for d in docs]
    assert activity == sorted(activity, reverse=True), "most recent activity first"
    recalls = client.get("/documents", params={"source": "fda_recalls", "since_days": 3650}, headers=HEADERS).json()
    assert recalls["documents"] and all(d["source"] == "fda_recalls" for d in recalls["documents"])


def test_failed_sources_are_reported_and_nothing_is_invented(client, service):
    service.set_transport(recorded_transport({h: 503 for h in ("api.fda.gov", "www.gdacs.org", "www.fda.gov",
                                                               "www.accessdata.fda.gov")}))
    result = client.post("/ingest", headers=HEADERS).json()
    assert result["documents_ingested"] == 0
    status = client.get("/sources", headers=HEADERS).json()
    assert {s["status"] for s in status["sources"].values()} == {"error"}
    assert status["total_documents"] == 0
    assert client.get("/documents", params={"since_days": 3650}, headers=HEADERS).json()["documents"] == []


def test_a_later_failure_keeps_the_last_success_time(client, service):
    client.post("/ingest", headers=HEADERS)
    service.set_transport(recorded_transport({"www.gdacs.org": 500}))
    client.post("/ingest", headers=HEADERS)
    gdacs = client.get("/sources", headers=HEADERS).json()["sources"]["gdacs"]
    assert gdacs["status"] == "error" and gdacs["last_success_at"]


def test_sources_list_never_run_sources(client):
    sources = client.get("/sources", headers=HEADERS).json()["sources"]
    assert {s["status"] for s in sources.values()} == {"never_run"}


def test_match_separates_incidents_from_exposures(client):
    client.post("/ingest", headers=HEADERS)
    suppliers = [
        {"id": "s-sun", "name": "Sun Pharmaceutical Industries, Inc.", "country_code": "IN"},
        {"id": "s-pfizer", "name": "Pfizer Inc.", "country_code": "US"},
        {"id": "s-none", "name": "Unrelated Widgets GmbH", "country_code": "DE"},
    ]
    body = client.post("/match", json={"suppliers": suppliers}, headers=HEADERS).json()
    sun = body["matches"]["s-sun"]
    assert any(m["kind"] == "incident" and m["signal"]["source"] == "fda_recalls" for m in sun)
    pfizer = body["matches"]["s-pfizer"]
    assert {m["match_type"] for m in pfizer} >= {"parent_company"}  # Hospira, a Pfizer company
    assert all(m["confidence"] >= 0.6 for m in pfizer if m["kind"] == "incident")
    # No company named like it; a disaster in its country is an exposure only.
    unrelated = body["matches"]["s-none"]
    assert all(m["kind"] == "exposure" and m["signal"]["signal_type"] == "disaster" for m in unrelated)


def test_match_honours_the_confidence_threshold(client):
    client.post("/ingest", headers=HEADERS)
    body = client.post("/match", json={"suppliers": [{"id": "p", "name": "Pfizer Inc."}], "min_confidence": 0.9},
                       headers=HEADERS).json()
    assert all(m["match_type"] != "parent_company" for m in body["matches"]["p"])


def test_endpoints_require_the_tenant_header(client):
    assert client.post("/ingest").status_code == 401
    assert client.post("/match", json={"suppliers": []}).status_code == 401


def test_a_long_running_shortage_counts_as_recent_activity():
    """A shortage first posted in 2012 but still listed (updated this month) is current;
    filtering it out by its posting date would hide an ongoing problem."""
    import asyncio
    from libs.common.store import MemoryStore

    store = MemoryStore(seed_demo=False)
    old_but_current = {"source": "fda_shortages", "external_id": "x", "signal_type": "shortage", "title": "Shortage: X",
                       "severity": "high", "entity_names": ["Hospira, Inc."], "entity_keys": ["hospira"],
                       "country_codes": [], "published_at": "2012-02-22", "updated_at": "2026-10-08"}
    stale_recall = {**old_but_current, "source": "fda_recalls", "external_id": "y", "signal_type": "recall",
                    "published_at": "2024-01-01", "updated_at": "2024-01-01"}

    async def check():
        await store.upsert_signals([old_but_current, stale_recall])
        recent, _ = await store.list_signals(since="2026-09-20")
        candidates = await store.signal_candidates(["hospira"], [], since="2026-09-20")
        return [s["external_id"] for s in recent], [s["external_id"] for s in candidates]

    assert asyncio.run(check()) == (["x"], ["x"])


class TestWatch:
    """The supplier watch flag is the back-tested recall-history rule (libs/intel/scoring.py)."""

    def recall(self, published, cls, event, match_type="name_exact", number=None):
        return {"match_type": match_type, "kind": "incident", "confidence": 0.95,
                "signal": {"signal_type": "recall", "published_at": published, "external_id": number or event,
                           "raw": {"event_id": event, "classification": cls}}}

    def test_one_event_counts_once_however_many_products(self, service):
        from datetime import date, timedelta
        recent = (date.today() - timedelta(days=20)).isoformat()
        batch = [self.recall(recent, "Class II", "e1", number=f"D-{i}") for i in range(12)]
        assert service._watch(batch)["recall_score"] == service._watch(batch[:1])["recall_score"]

    def test_threshold_and_parent_company_matches(self, service):
        from datetime import date, timedelta
        recent = (date.today() - timedelta(days=20)).isoformat()
        serious = [self.recall(recent, "Class I", "e1")]
        assert service._watch(serious)["watch"] is True
        assert service._watch([self.recall(recent, "Class III", "e2")])["watch"] is False
        for weaker in ("parent_company", "name_contains", "name_similar"):
            assert service._watch([self.recall(recent, "Class I", "e3", match_type=weaker)]) == \
                {"recall_score": 0.0, "watch": False}

    def test_other_record_types_do_not_score(self, service):
        from datetime import date
        letter = {"match_type": "name_exact", "kind": "incident", "confidence": 0.95,
                  "signal": {"signal_type": "warning_letter", "published_at": date.today().isoformat(), "raw": {}}}
        assert service._watch([letter])["recall_score"] == 0.0


class TestDelisting:
    """Shortages and import alerts are current lists: what FDA drops must stop showing."""

    def shortages_without(self, company_prefix):
        import json
        from intel_support import fixture

        body = fixture("fda_shortages.json")
        body["results"] = [r for r in body["results"] if not r["company_name"].startswith(company_prefix)]

        def handler(request):
            if request.url.path.endswith("/shortages.json"):
                return httpx.Response(200, json=body)
            return recorded_transport().handle_request(request)

        return httpx.MockTransport(handler)

    def hospira_shortages(self, client):
        docs = client.get("/documents", params={"source": "fda_shortages", "since_days": 36500, "limit": 500},
                          headers=HEADERS).json()["documents"]
        return [d for d in docs if d["entity_names"][0].startswith("Hospira")]

    def test_entries_fda_no_longer_lists_are_delisted(self, client, service):
        client.post("/ingest", headers=HEADERS)
        assert self.hospira_shortages(client)
        service.set_transport(self.shortages_without("Hospira"))
        result = client.post("/ingest", headers=HEADERS).json()["sources"]["fda_shortages"]
        assert result["status"] == "ok" and result["delisted"] > 0
        assert self.hospira_shortages(client) == []
        matches = client.post("/match", json={"suppliers": [{"id": "h", "name": "Hospira, Inc."}]},
                              headers=HEADERS).json()["matches"]["h"]
        assert not any(m["signal"]["source"] == "fda_shortages" for m in matches)

    def test_relisting_restores_an_entry(self, client, service):
        client.post("/ingest", headers=HEADERS)
        service.set_transport(self.shortages_without("Hospira"))
        client.post("/ingest", headers=HEADERS)
        service.set_transport(recorded_transport())
        client.post("/ingest", headers=HEADERS)
        assert self.hospira_shortages(client)

    def test_a_list_that_collapses_is_an_error_and_retires_nothing(self, client, service):
        client.post("/ingest", headers=HEADERS)
        before = len(self.hospira_shortages(client))
        service.set_transport(self.shortages_without(""))  # every entry gone: a broken fetch, not mass delisting
        result = client.post("/ingest", headers=HEADERS).json()["sources"]["fda_shortages"]
        assert result["status"] == "error" and "nothing retired" in result["error"]
        assert len(self.hospira_shortages(client)) == before

    def test_event_sources_are_never_delisted(self, client, service):
        client.post("/ingest", headers=HEADERS)
        service.set_transport(recorded_transport({"api.fda.gov": 404}))  # "no matches" for recalls
        result = client.post("/ingest", headers=HEADERS).json()["sources"]["fda_recalls"]
        assert result["delisted"] == 0
        recalls = client.get("/documents", params={"source": "fda_recalls", "since_days": 36500}, headers=HEADERS).json()
        assert recalls["documents"]


def test_evidence_ask_cites_records_and_scopes_empty_answers(client):
    client.post("/ingest", headers=HEADERS)
    sun = {"id": "s", "name": "Sun Pharmaceutical Industries, Inc."}
    answered = client.post("/evidence/ask", json={"question": "Any recalls?", "supplier": sun}, headers=HEADERS).json()
    assert answered["status"] == "answered" and answered["claims"] and answered["citations"]
    assert all(c["citations"] for c in answered["claims"])
    unknown = client.post("/evidence/ask", json={"question": "Any recalls?", "supplier": {"name": "Nowhere Pharma Ltd"}},
                          headers=HEADERS).json()
    assert unknown["status"] == "no_records" and "does not mean nothing happened" in unknown["note"]
    assert client.post("/evidence/ask", json={"question": "Any recalls?", "supplier": sun}).status_code == 401
