"""
Vector search plumbing: storage and invalidation, exact supplier-scoped search,
fusion with keyword results, the distance cut-off, and the separate embedding
step in ingestion.

The embedder here is a test fake that maps a few concepts to fixed directions.
It checks the plumbing only. Retrieval quality with real Cohere embeddings is
measured separately (evals/evidence, set C) once AWS access exists.
"""

import asyncio
import importlib.util
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("ENVIRONMENT", "test")

import pg_support  # noqa: E402
from libs.common.store import MemoryStore, text_hash  # noqa: E402
from libs.evidence import embeddings, retrieval  # noqa: E402

DIM = embeddings.EMBEDDING_DIM
CONCEPTS = {
    0: ("particulate", "particles", "floating", "bits", "specks", "glass"),
    1: ("sterility", "sterile", "microbes", "germs", "bacteria"),
    2: ("label", "labeling", "mislabeled", "wrong", "mix-up"),
    3: ("subpotent", "weaker", "potency", "strength"),
}


class FakeEmbedder:
    model_id = "test-fake-embedder"
    dimension = DIM

    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def _vector(self, text):
        words = text.lower().replace(".", " ").replace(":", " ").split()
        v = [0.0] * DIM
        for dim, vocab in CONCEPTS.items():
            v[dim] = float(sum(any(w.startswith(t) for t in vocab) for w in words))
        v[DIM - 1] = 0.05  # never a zero vector
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v]

    async def embed_documents(self, texts):
        if self.fail:
            raise RuntimeError("ThrottlingException")
        self.calls.append(("documents", len(texts)))
        return [self._vector(t) for t in texts]

    async def embed_query(self, text):
        self.calls.append(("query", 1))
        return self._vector(text)


def recall(eid, summary, firm="Acme Pharma Inc.", key="acme", cls="Class II", title="Class II recall: Saline"):
    return {"source": "fda_recalls", "external_id": eid, "signal_type": "recall", "severity": "high",
            "title": title, "summary": f"{firm}: {summary}", "entity_names": [firm], "entity_keys": [key],
            "country_codes": ["US"], "published_at": "2026-05-01", "updated_at": "2026-05-01",
            "raw": {"classification": cls, "recalling_firm": firm, "reason_for_recall": summary}}


PARTICULATE = recall("r1", "Presence of Particulate Matter: visible particles observed.")
LABEL = recall("r2", "Labeling: Label Mix-up on carton.")
OTHER_FIRM = recall("r3", "Presence of Particulate Matter.", firm="Zeta Labs LLC", key="zeta")


async def embed_all(store, embedder):
    pending = await store.signals_needing_embedding(embedder.model_id)
    vectors = await embedder.embed_documents([embeddings.document_text(r) for r in pending])
    return await store.set_embeddings([(r["id"], text_hash(r), v) for r, v in zip(pending, vectors)], embedder.model_id)


@pytest.fixture
def store():
    s = MemoryStore(seed_demo=False)
    asyncio.run(s.upsert_signals([PARTICULATE, LABEL, OTHER_FIRM]))
    asyncio.run(embed_all(s, FakeEmbedder()))
    return s


SUPPLIER = {"name": "Acme Pharma Inc."}


class TestHybridRetrieval:
    def ask(self, store, question, embedder=FakeEmbedder()):
        return asyncio.run(retrieval.retrieve(store, question, SUPPLIER, embedder=embedder))

    def test_a_described_defect_keyword_search_cannot_parse_is_found(self, store):
        question = "Did the liquid have bits floating in it?"
        assert self.ask(store, question, embedder=None)["mode"] == "general"  # keyword-only falls back to everything
        got = self.ask(store, question)
        assert got["mode"] == "vector" and [r["record"]["external_id"] for r in got["results"]] == ["r1"]

    def test_only_the_suppliers_records_are_searched(self, store):
        got = self.ask(store, "Did the liquid have bits floating in it?")
        assert all(r["record"]["entity_keys"] == ["acme"] for r in got["results"])

    def test_nothing_close_enough_returns_nothing(self, store):
        assert self.ask(store, "Were there germs found in the bacteria tests?")["results"] == []

    def test_keyword_and_vector_results_are_fused(self, store):
        got = self.ask(store, "Any labeling problems or bits floating in the vials?")
        assert got["mode"] == "hybrid"
        assert {r["record"]["external_id"] for r in got["results"]} == {"r1", "r2"}

    def test_type_filter_applies_to_vector_hits(self, store):
        got = self.ask(store, "Any warning letters about particles?")
        assert got["results"] == []  # the supplier's particulate records are recalls, not letters

    def test_an_embedding_failure_leaves_keyword_results(self, store):
        class Broken(FakeEmbedder):
            async def embed_query(self, text):
                raise RuntimeError("ThrottlingException")
        got = self.ask(store, "Any labeling problems?", embedder=Broken())
        assert got["mode"] == "keyword" and [r["record"]["external_id"] for r in got["results"]] == ["r2"]


class TestEmbeddingLifecycleMemory:
    def test_changed_text_needs_a_new_vector(self, store):
        model = FakeEmbedder.model_id
        assert asyncio.run(store.signals_needing_embedding(model)) == []
        asyncio.run(store.upsert_signals([{**LABEL, "summary": "Acme Pharma Inc.: Labeling: Incorrect Expiration Date."}]))
        assert [r["title"] for r in asyncio.run(store.signals_needing_embedding(model))] == [LABEL["title"]]
        assert asyncio.run(store.embedding_coverage(model)) == {"embedded": 2, "total": 3}

    def test_vectors_from_another_model_are_ignored(self, store):
        hits = asyncio.run(store.vector_search([1.0] + [0.0] * (DIM - 1), "another-model", ["acme"]))
        assert hits == []


@pytest.mark.skipif(not pg_support.postgres_url(), reason="TEST_POSTGRES_URL not set")
class TestPostgresVectors:
    @pytest.fixture(scope="class")
    def pg(self):
        urls = pg_support.fresh_database("scirm_test_vectors", seed_demo=False)
        os.environ["DB_POOL"] = "null"
        return urls["app"]

    def run(self, pg, steps):
        from libs.common.store import PostgresStore

        async def go():
            store = PostgresStore(pg)
            try:
                return await steps(store)
            finally:
                await store.close()
        return asyncio.run(go())

    def test_store_search_invalidate_and_scope(self, pg):
        embedder = FakeEmbedder()

        async def steps(store):
            await store.upsert_signals([PARTICULATE, LABEL, OTHER_FIRM])
            written = await embed_all(store, embedder)
            query = await embedder.embed_query("bits floating in the liquid")
            near = await store.vector_search(query, embedder.model_id, ["acme"], limit=5)
            other_model = await store.vector_search(query, "another-model", ["acme"])
            # A text change drops the vector; a stale write (hash mismatch) is skipped.
            await store.upsert_signals([{**PARTICULATE, "summary": "Acme Pharma Inc.: Glass particles found."}])
            pending = await store.signals_needing_embedding(embedder.model_id)
            stale = await store.set_embeddings([(pending[0]["id"], "not-the-hash", query)], embedder.model_id)
            coverage = await store.embedding_coverage(embedder.model_id)
            await store.retire_unseen("fda_recalls", ["r2", "r3", "r1"])
            return written, near, other_model, pending, stale, coverage

        written, near, other_model, pending, stale, coverage = self.run(pg, steps)
        assert written == 3
        assert [r["external_id"] for r in near][:1] == ["r1"] and {r["external_id"] for r in near} == {"r1", "r2"}
        assert "embedding" not in near[0] and other_model == []
        assert [p["title"] for p in pending] == [PARTICULATE["title"]] and stale == 0
        assert coverage == {"embedded": 2, "total": 3}

    def test_delisted_records_are_not_searched(self, pg):
        embedder = FakeEmbedder()

        async def steps(store):
            await store.upsert_signals([{**LABEL, "source": "fda_import_alerts", "external_id": "ia-1",
                                         "signal_type": "import_alert"}])
            await embed_all(store, embedder)
            await store.retire_unseen("fda_import_alerts", [])
            return await store.vector_search(await embedder.embed_query("label mix-up"), embedder.model_id, ["acme"])

        assert all(r["external_id"] != "ia-1" for r in self.run(pg, steps))


class TestIngestionEmbeddingStep:
    def load(self, monkeypatch, embedder):
        import httpx
        from intel_support import recorded_transport
        previous = os.environ.get("STORE_BACKEND")
        os.environ["STORE_BACKEND"] = "memory"
        try:
            spec = importlib.util.spec_from_file_location("vec_ingestion", ROOT / "services" / "ingestion" / "main.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            if previous is None:
                os.environ.pop("STORE_BACKEND", None)
            else:
                os.environ["STORE_BACKEND"] = previous
        monkeypatch.setattr(module, "http_client_factory", lambda: httpx.AsyncClient(transport=recorded_transport()))
        monkeypatch.setattr(module, "LOOKBACK_DAYS", 36500)
        monkeypatch.setattr(module, "embedder", embedder)
        return module

    def test_ingestion_embeds_and_reports_coverage(self, monkeypatch):
        from fastapi.testclient import TestClient
        module = self.load(monkeypatch, FakeEmbedder())
        client, headers = TestClient(module.app), {"X-Org-Id": "a0000000-0000-0000-0000-000000000001"}
        client.post("/ingest", headers=headers)
        vectors = client.get("/sources", headers=headers).json()["embeddings"]
        assert vectors["status"] == "on" and vectors["embedded"] == vectors["total"] > 0

    def test_an_embedding_failure_does_not_fail_ingestion(self, monkeypatch):
        from fastapi.testclient import TestClient
        module = self.load(monkeypatch, FakeEmbedder(fail=True))
        client, headers = TestClient(module.app), {"X-Org-Id": "a0000000-0000-0000-0000-000000000001"}
        result = client.post("/ingest", headers=headers).json()
        assert {v["status"] for v in result["sources"].values()} == {"ok"}
        assert client.get("/sources", headers=headers).json()["embeddings"]["embedded"] == 0

    def test_without_an_embedder_vectors_are_off(self, monkeypatch):
        from fastapi.testclient import TestClient
        module = self.load(monkeypatch, None)
        client = TestClient(module.app)
        assert client.get("/sources", headers={"X-Org-Id": "x"}).json()["embeddings"] == {"status": "disabled"}
