"""
Fixtures for the AI-trust regression suite: helpers to load individual services
in-process and to route their outbound HTTP calls to other in-process services.
"""

import importlib.util
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]

# No LLM keys: every test runs the deterministic paths unless it mocks the LLM.
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("ENVIRONMENT", "test")
sys.path.insert(0, str(ROOT))


def _load_service(name: str):
    """Load services/<name>/main.py as a fresh module."""
    path = ROOT / "services" / name / "main.py"
    spec = importlib.util.spec_from_file_location(f"ai_trust_{name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    # These tests inspect the in-memory store; force it even if a run selected postgres.
    previous = os.environ.get("STORE_BACKEND")
    os.environ["STORE_BACKEND"] = "memory"
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            os.environ.pop("STORE_BACKEND", None)
        else:
            os.environ["STORE_BACKEND"] = previous
    return module


class PortRouter(httpx.AsyncBaseTransport):
    """Routes requests to in-process ASGI apps by port; unknown ports are unreachable."""

    def __init__(self, apps_by_port):
        self._transports = {port: httpx.ASGITransport(app=app) for port, app in apps_by_port.items()}

    async def handle_async_request(self, request):
        transport = self._transports.get(request.url.port)
        if transport is None:
            raise httpx.ConnectError(f"connection refused: {request.url}", request=request)
        return await transport.handle_async_request(request)


@pytest.fixture(scope="session")
def load_service():
    # A fixture, not an import: sibling test folders each have a conftest.py.
    return _load_service


@pytest.fixture
def router_factory():
    return PortRouter


@pytest.fixture
def llm(monkeypatch):
    """Make the shared LLM client look configured and control what it returns."""
    from libs.common import llm as llm_client

    class Controller:
        def succeed_with(self, payload):
            async def fake_generate(prompt, system=None, **kwargs):
                llm_client._record("calls")
                import json
                return json.dumps(payload)
            monkeypatch.setattr(llm_client, "generate", fake_generate)

        def fail(self):
            async def failing_generate(prompt, system=None, **kwargs):
                llm_client._record("failures")
                raise RuntimeError("LLM unavailable")
            monkeypatch.setattr(llm_client, "generate", failing_generate)

    monkeypatch.setattr(llm_client, "is_configured", lambda: True)
    return Controller()
