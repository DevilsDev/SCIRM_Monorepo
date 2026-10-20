"""
Sample-data features (simulators, procurement alternatives, components, 7-day predictions,
the rule-based risk score) are refused unless SAMPLE_FEATURES is on. It is on by default
only in development and test, so a pilot never sees sample output presented as analysis.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_REQUESTS = [
    ("get", "/api/v1/predictions"),
    ("post", "/api/v1/scenarios/simulate"),
    ("post", "/api/v1/simulator/run"),
    ("post", "/api/v1/procurement/evaluate"),
    ("get", "/api/v1/procurement/actions"),
    ("get", "/api/v1/procurement/alternatives/Supplier%20Alpha"),
    ("get", "/api/v1/components"),
    ("get", "/api/v1/components/comp-001/impact"),
    ("get", "/api/v1/products"),
    ("get", "/api/v1/products/p1/bom"),
    ("post", "/api/v1/risk-score"),
    ("get", "/api/v1/risk-dimensions"),
]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_features_off(apps, monkeypatch):
    monkeypatch.setattr(apps["gateway"], "SAMPLE_FEATURES", False)


@pytest.mark.parametrize("method,path", SAMPLE_REQUESTS)
def test_sample_endpoints_are_refused_when_off(client, sarah, sample_features_off, method, path):
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, headers=bearer(sarah["access_token"]), **kwargs)
    assert response.status_code == 404 and response.json()["detail"] == "This feature is not available"


def test_config_reports_the_switch(client, sarah, apps, monkeypatch):
    assert client.get("/api/v1/config", headers=bearer(sarah["access_token"])).json() == {"features": {"sample_pages": True}}
    monkeypatch.setattr(apps["gateway"], "SAMPLE_FEATURES", False)
    assert client.get("/api/v1/config", headers=bearer(sarah["access_token"])).json() == {"features": {"sample_pages": False}}


def test_config_needs_sign_in(client):
    assert client.get("/api/v1/config").status_code in (401, 403)


def test_real_features_are_unaffected(client, sarah, sample_features_off):
    assert client.get("/api/v1/suppliers", headers=bearer(sarah["access_token"])).status_code == 200
    # A path that only starts with a gated word is not gated.
    assert client.get("/api/v1/predictionsX", headers=bearer(sarah["access_token"])).status_code == 404
    assert client.get("/api/v1/alerts", headers=bearer(sarah["access_token"])).status_code == 200


def test_off_by_default_outside_development():
    code = (
        f"import sys, importlib.util; sys.path.insert(0, r'{ROOT}');"
        f"s = importlib.util.spec_from_file_location('gw', r'{ROOT / 'apps/api-gateway/main.py'}');"
        "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.SAMPLE_FEATURES)"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("DEV_PASSWORD", "SAMPLE_FEATURES")}
    env.update({"ENVIRONMENT": "staging", "JWT_SECRET_KEY": "k" * 40, "SERVICE_API_KEY": "svc-key",
                "STORE_BACKEND": "postgres", "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/unused"})
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("False")
