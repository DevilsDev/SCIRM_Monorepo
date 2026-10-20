"""
Fixtures for the security test suite.

Runs the API gateway together with the coordinator, procurement and chat
services in one process: the gateway's outbound httpx calls are routed to the
services' ASGI apps by port, so the full gateway → service path (including the
tenant headers) is exercised without any network or Docker.
"""

import importlib.util
import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]

# Configuration is read at import time, so it must be set before loading any app.
os.environ["ENVIRONMENT"] = "test"
os.environ["DEV_PASSWORD"] = "test-dev-password"
os.environ["MFA_ENABLED"] = "true"
# The suite makes far more requests from one client than a person would.
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["RATE_LIMIT_BURST"] = "100000"
os.environ.pop("JWT_SECRET_KEY", None)
os.environ.pop("SERVICE_API_KEY", None)
sys.path.insert(0, str(ROOT))

# The suite runs against either backend: STORE_BACKEND=memory (default) or
# STORE_BACKEND=postgres with TEST_POSTGRES_URL — same tests, proving parity.
STORE_BACKEND = os.environ.setdefault("STORE_BACKEND", "memory")
if STORE_BACKEND == "postgres":
    sys.path.insert(0, str(ROOT / "tests"))
    import pg_support

    if not pg_support.postgres_url():
        raise RuntimeError("STORE_BACKEND=postgres needs TEST_POSTGRES_URL (a superuser URL)")
    _urls = pg_support.fresh_database("scirm_test_security")
    # Services connect as the restricted role, exactly as in production.
    os.environ["DATABASE_URL"] = _urls["app"]
    os.environ["DB_POOL"] = "null"

DEV_PASSWORD = os.environ["DEV_PASSWORD"]
ORG_1 = "a0000000-0000-0000-0000-000000000001"
ORG_2 = "a0000000-0000-0000-0000-000000000002"


def _load(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortRouter(httpx.AsyncBaseTransport):
    """Routes requests to in-process ASGI apps by destination port, recording headers."""

    def __init__(self, apps_by_port):
        self._transports = {port: httpx.ASGITransport(app=app) for port, app in apps_by_port.items()}
        self.seen_headers = []

    async def handle_async_request(self, request):
        self.seen_headers.append(dict(request.headers))
        return await self._transports[request.url.port].handle_async_request(request)


@pytest.fixture(scope="session")
def apps():
    coordinator = _load("scirm_coordinator", "services/coordinator/main.py")
    procurement = _load("scirm_procurement", "services/procurement/main.py")
    chat = _load("scirm_chat", "services/chat/main.py")
    ingestion = _load("scirm_ingestion", "services/ingestion/main.py")
    gateway = _load("scirm_gateway", "apps/api-gateway/main.py")

    router = PortRouter({8001: coordinator.app, 8008: ingestion.app, 8009: chat.app, 8011: procurement.app})
    real_client = httpx.AsyncClient

    def routed_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=router, **kwargs)

    class GatewayHttpx:
        """Stands in for the httpx module inside the gateway only, so the patch
        doesn't leak into other test modules through the shared httpx module."""
        AsyncClient = staticmethod(routed_client)

        def __getattr__(self, name):
            return getattr(httpx, name)

    gateway.httpx = GatewayHttpx()
    chat._http = real_client(transport=router, timeout=15.0)
    coordinator._http_client = real_client(transport=router, timeout=15.0)
    # Public sources are served from recorded payloads, never the network.
    sys.path.insert(0, str(ROOT / "tests"))
    from intel_support import recorded_transport
    ingestion.http_client_factory = lambda: real_client(transport=recorded_transport())
    ingestion.LOOKBACK_DAYS = 36500  # recorded payloads have fixed dates

    return {"gateway": gateway, "coordinator": coordinator, "ingestion": ingestion, "router": router}


@pytest.fixture(scope="session")
def client(apps):
    return TestClient(apps["gateway"].app)


@pytest.fixture(scope="session")
def login(client):
    def _login(email, password=DEV_PASSWORD):
        return client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return _login


def _tokens(login, email):
    response = login(email)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="session")
def sarah(login):
    """Admin in org 1."""
    return _tokens(login, "sarah.chen@pharmacorp.com")


@pytest.fixture(scope="session")
def lisa(login):
    """Admin in org 2."""
    return _tokens(login, "lisa.park@medtech.com")


@pytest.fixture(scope="session")
def auditor(login):
    """Read-only auditor/viewer."""
    return _tokens(login, "auditor@scirm.dev")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
