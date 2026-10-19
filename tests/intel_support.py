"""Recorded public-source payloads (tests/fixtures/intel) served over a mock transport."""

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "intel"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def recorded_transport(overrides=None):
    """Serve the recorded payloads; `overrides` maps a host to a status code."""
    overrides = overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        for host, status in overrides.items():
            if request.url.host == host:
                return httpx.Response(status, json={"error": "simulated"})
        if request.url.path.endswith("/enforcement.json"):
            return httpx.Response(200, json=fixture("fda_enforcement.json"))
        if request.url.path.endswith("/shortages.json"):
            return httpx.Response(200, json=fixture("fda_shortages.json"))
        if "gdacs" in request.url.host:
            return httpx.Response(200, json=fixture("gdacs.json"))
        return httpx.Response(404)

    return httpx.MockTransport(handler)
