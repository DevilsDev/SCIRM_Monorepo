"""Recorded public-source payloads (tests/fixtures/intel) served over a mock transport."""

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "intel"
# An alert page with no Red List, for alerts whose page was not recorded.
EMPTY_ALERT_PAGE = "<html><body><h3>Import Alert</h3><p>No firms listed.</p></body></html>"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def recorded_transport(overrides=None):
    """Serve the recorded payloads; `overrides` maps a host to a status code."""
    overrides = overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        for host, status in overrides.items():
            if request.url.host == host:
                return httpx.Response(status, json={"error": "simulated"})
        path = request.url.path
        if path.endswith("/enforcement.json"):
            return httpx.Response(200, json=fixture("fda_enforcement.json"))
        if path.endswith("/shortages.json"):
            return httpx.Response(200, json=fixture("fda_shortages.json"))
        if "gdacs" in request.url.host:
            return httpx.Response(200, json=fixture("gdacs.json"))
        if request.url.host == "www.fda.gov" and path.startswith("/datatables/"):
            return httpx.Response(200, json=fixture("warning_letters.json"))
        if request.url.host == "www.accessdata.fda.gov":
            if path.endswith("/ialist.html"):
                return httpx.Response(200, text=fixture_text("import_alert_list.html"))
            if path.endswith("/importalert_189.html"):
                return httpx.Response(200, text=fixture_text("import_alert_66_40.html"))
            if "/importalert_" in path:
                return httpx.Response(200, text=EMPTY_ALERT_PAGE)
        return httpx.Response(404)

    return httpx.MockTransport(handler)
