"""
Regression tests: the platform must never present missing, failed or sample data
as real intelligence. Each test pins a specific fabricated-output bug from the
October 2026 review.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from libs.common import llm as llm_client

ORG = "a0000000-0000-0000-0000-000000000001"
ENTITY = {"id": "c0000000-0000-0000-0000-000000000003", "name": "Supplier Gamma", "type": "supplier", "location": "Shenzhen, CN"}
ASSESSMENT = {"entities": [ENTITY], "assessment_type": "comprehensive"}


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class TestExecutor:
    @pytest.fixture(scope="class")
    def executor(self, load_service):
        return load_service("executor")

    def test_critical_findings_become_risks(self, executor):
        client = TestClient(executor.app)
        response = client.post("/generate-recommendations", json={
            "request": ASSESSMENT,
            "context": {},
            "research_data": {"findings": [
                {"risk_level": "critical", "type": "logistics", "key_insights": ["Export port closed"], "source": "news"},
                {"risk_level": "low", "type": "financial", "key_insights": ["Minor rating change"], "source": "news"},
            ]},
        })
        assert response.status_code == 200, response.text
        severities = [r["severity"] for r in response.json()["risks"]]
        assert "critical" in severities

    def test_unexpected_priority_does_not_crash(self, executor):
        from libs.common.models import Recommendation
        recs = [Recommendation(id="r1", risk_id="x", title="Act now", description="d", action_type="preventive",
                               priority="critical", estimated_impact=5.0, success_probability=0.5)]
        matrix = executor.executor_agent._create_priority_matrix(recs)
        assert matrix["high"] == ["Act now"]


# ---------------------------------------------------------------------------
# Coordinator: degraded-result contract
# ---------------------------------------------------------------------------

class TestCoordinatorDegradedResults:
    @pytest.fixture(scope="class")
    def services(self, load_service):
        return {name: load_service(name) for name in ("coordinator", "planner", "executor", "reviewer", "researcher")}

    def _client(self, services, router_factory, available):
        ports = {"planner": 8002, "researcher": 8003, "executor": 8004, "reviewer": 8005}
        coordinator = services["coordinator"]
        coordinator._http_client = httpx.AsyncClient(
            transport=router_factory({ports[n]: services[n].app for n in available}))
        return TestClient(coordinator.app), coordinator

    def test_full_pipeline_is_not_degraded_by_agents(self, services, router_factory):
        client, _ = self._client(services, router_factory, ["planner", "researcher", "executor", "reviewer"])
        response = client.post("/assess-risk", json=ASSESSMENT, headers={"X-Org-Id": ORG})
        assert response.status_code == 200, response.text
        quality = response.json()["metadata"]["data_quality"]
        assert quality["unavailable_agents"] == []
        # Without a vector store the researcher uses its sample corpus — that must be disclosed.
        assert any("sample corpus" in w for w in quality["warnings"])
        assert quality["degraded"] is True

    def test_missing_researcher_marks_result_degraded(self, services, router_factory):
        client, _ = self._client(services, router_factory, ["planner", "executor", "reviewer"])
        response = client.post("/assess-risk", json=ASSESSMENT, headers={"X-Org-Id": ORG})
        assert response.status_code == 200, response.text
        quality = response.json()["metadata"]["data_quality"]
        assert quality["degraded"] is True
        assert quality["unavailable_agents"] == ["researcher"]

    def test_missing_required_agent_fails_instead_of_empty_success(self, services, router_factory):
        client, coordinator = self._client(services, router_factory, ["planner", "researcher", "reviewer"])
        response = client.post("/assess-risk", json=ASSESSMENT, headers={"X-Org-Id": ORG})
        assert response.status_code == 503
        failed = [t for t in coordinator.store.tasks.values() if t.get("status") == "failed"]
        assert failed, "the task must be recorded as failed, not completed"

    def test_unavailable_discovery_is_an_error_not_an_empty_list(self, services, router_factory):
        client, _ = self._client(services, router_factory, [])
        response = client.post("/discover-subtiers", json={"supplier_name": "Supplier Gamma"}, headers={"X-Org-Id": ORG})
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class TestChat:
    @pytest.fixture(scope="class")
    def chat(self, load_service):
        return load_service("chat")

    def _set_coordinator(self, chat, router_factory, app=None):
        chat._http = httpx.AsyncClient(transport=router_factory({8001: app} if app else {}), timeout=5.0)

    @pytest.mark.parametrize("message", ["show high risk items", "any active alerts?", "list suppliers"])
    def test_unreachable_data_is_never_reported_as_all_clear(self, chat, router_factory, message):
        self._set_coordinator(chat, router_factory)
        body = TestClient(chat.app).post("/chat", json={"message": message}, headers={"X-Org-Id": ORG}).json()
        assert body["degraded"] is True
        assert "not an all-clear" in body["reply"]
        assert "healthy" not in body["reply"].lower()

    def test_error_responses_are_not_read_as_empty_data(self, chat, router_factory):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        broken = FastAPI()

        @broken.get("/risks")
        async def risks():
            return JSONResponse({"detail": "internal error"}, status_code=500)

        self._set_coordinator(chat, router_factory, broken)
        body = TestClient(chat.app).post("/chat", json={"message": "show high risk items"}, headers={"X-Org-Id": ORG}).json()
        assert body["degraded"] is True

    def test_no_recorded_risks_does_not_claim_health(self, chat, router_factory):
        from fastapi import FastAPI
        empty = FastAPI()

        @empty.get("/risks")
        async def risks():
            return {"risks": [], "total": 0}

        self._set_coordinator(chat, router_factory, empty)
        body = TestClient(chat.app).post("/chat", json={"message": "show high risk items"}, headers={"X-Org-Id": ORG}).json()
        assert body["degraded"] is False
        assert "healthy" not in body["reply"].lower()
        assert "assessment" in body["reply"].lower()

    def test_unassessed_suppliers_are_not_given_a_score(self, chat, router_factory):
        from fastapi import FastAPI
        coordinator = FastAPI()

        @coordinator.get("/suppliers")
        async def suppliers():
            return {"suppliers": [{"name": "Acme", "country_code": "DE", "risk_score": None, "risk_tier": None}]}

        self._set_coordinator(chat, router_factory, coordinator)
        body = TestClient(chat.app).post("/chat", json={"message": "list suppliers"}, headers={"X-Org-Id": ORG}).json()
        assert "not assessed" in body["reply"] and "/100" not in body["reply"]

    def test_predictions_are_not_offered_when_sample_features_are_off(self, chat, router_factory, monkeypatch):
        monkeypatch.setattr(chat, "SAMPLE_FEATURES", False)
        self._set_coordinator(chat, router_factory)
        body = TestClient(chat.app).post("/chat", json={"message": "predict disruption next week"},
                                         headers={"X-Org-Id": ORG}).json()
        assert "predict" not in body["reply"].lower() and body["degraded"] is False


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDiscovery:
    @pytest.fixture
    def discovery(self, load_service):
        return load_service("discovery")

    def test_llm_subtiers_are_labelled_unconfirmed_suggestions(self, discovery, llm):
        llm.succeed_with({"subtiers": [{"name": "Plausible Foil Co", "type": "sub_supplier", "country": "CN", "tier": 2, "confidence": 0.95}]})
        body = TestClient(discovery.app).post("/discover", json={"supplier_name": "Supplier Gamma"}).json()
        assert body["discovery_method"] == "llm_suggestion"
        assert body["verification_status"] == "unconfirmed"
        sub = body["discovered_subtiers"][0]
        assert sub["verification_status"] == "unconfirmed"
        assert sub["confidence"] <= 0.5
        assert all(r["verification_status"] == "unconfirmed" for r in body["relationships"])

    def test_method_reflects_what_ran_when_llm_fails(self, discovery, llm):
        llm.fail()
        body = TestClient(discovery.app).post("/discover", json={"supplier_name": "Supplier Gamma"}).json()
        assert body["discovery_method"] in ("knowledge_base", "none")
        assert body["discovery_method"] != "llm_suggestion"


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class TestIngestion:
    """The feed used to fall back to built-in sample items; now it holds only public records."""

    @pytest.fixture
    def ingestion(self, monkeypatch, load_service):
        module = load_service("ingestion")

        def unreachable(request):
            raise httpx.ConnectError("no network", request=request)

        monkeypatch.setattr(module, "http_client_factory",
                            lambda: httpx.AsyncClient(transport=httpx.MockTransport(unreachable)))
        return module

    def test_unreachable_sources_yield_an_empty_feed_not_sample_items(self, ingestion):
        client = TestClient(ingestion.app)
        headers = {"X-Org-Id": "a0000000-0000-0000-0000-000000000001"}
        assert client.post("/ingest", headers=headers).json()["documents_ingested"] == 0
        assert client.get("/documents", params={"since_days": 3650}, headers=headers).json()["documents"] == []
        statuses = {v["status"] for v in client.get("/sources", headers=headers).json()["sources"].values()}
        assert statuses == {"error"}


# ---------------------------------------------------------------------------
# ERP
# ---------------------------------------------------------------------------

class TestERP:
    @pytest.fixture
    def manager_module(self):
        import libs.integrations.manager as manager
        return manager

    async def _suppliers(self, manager_module):
        return await manager_module.ERPManager().sync_suppliers(ORG)

    def test_demo_records_are_tagged(self, manager_module, monkeypatch):
        import asyncio
        monkeypatch.setattr(manager_module, "ERP_DEMO_DATA", True)
        suppliers = asyncio.run(self._suppliers(manager_module))
        assert suppliers and all(s["is_demo"] for s in suppliers)

    def test_demo_records_excluded_when_disabled(self, manager_module, monkeypatch):
        import asyncio
        monkeypatch.setattr(manager_module, "ERP_DEMO_DATA", False)
        assert asyncio.run(self._suppliers(manager_module)) == []
        results = asyncio.run(manager_module.ERPManager().sync_all(ORG))
        assert all(r == {"status": "not_connected"} for r in results.values())


# ---------------------------------------------------------------------------
# "LLM used" flags report what actually ran
# ---------------------------------------------------------------------------

class TestLLMFlags:
    @pytest.fixture
    def scorer(self, load_service):
        return load_service("risk-scorer")

    def test_scorer_not_enhanced_without_llm(self, scorer):
        body = TestClient(scorer.app).post("/score", json={"supplier_name": "Supplier Gamma", "supplier_context": {}}).json()
        assert body["llm_enhanced"] is False
        assert all(d["method"] == "rules" for d in body["dimension_scores"])

    def test_scorer_not_enhanced_when_llm_fails(self, scorer, llm):
        llm.fail()
        body = TestClient(scorer.app).post("/score", json={"supplier_name": "Supplier Gamma", "supplier_context": {}}).json()
        assert body["llm_enhanced"] is False

    def test_scorer_enhanced_when_llm_succeeds(self, scorer, llm):
        llm.succeed_with({"score": 70, "confidence": 0.8, "trend": "rising", "reasoning": "r", "key_factors": []})
        body = TestClient(scorer.app).post("/score", json={"supplier_name": "Supplier Gamma", "supplier_context": {}}).json()
        assert body["llm_enhanced"] is True

    def test_planner_flag_false_when_llm_fails(self, llm, load_service):
        planner = load_service("planner")
        llm.fail()
        response = TestClient(planner.app).post("/analyze-context", json={"request": ASSESSMENT})
        assert response.status_code == 200, response.text
        assert response.json()["metadata"]["llm_enhanced"] is False

    def test_usage_tracking_counts_calls(self):
        with llm_client.track_usage() as usage:
            llm_client._record("calls")
            llm_client._record("failures")
        assert usage == {"calls": 1, "failures": 1}
        llm_client._record("calls")  # outside a scope: ignored, no error
