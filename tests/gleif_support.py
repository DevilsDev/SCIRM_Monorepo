"""A fake GLEIF API serving responses recorded from api.gleif.org on 2026-10-26 (CC0 1.0).

Recorded: LONZA VERVIERS (reports LONZA GROUP AG as direct and ultimate parent), LONZA GROUP
AG (reports NON_CONSOLIDATING exceptions), LONZA BRAINE SA (reports neither) and a search
for "Lonza" in Belgium. Anything else is a 404, as GLEIF answers for an unknown LEI.
"""

import json
from pathlib import Path

import httpx

RECORDED = json.loads((Path(__file__).parent / "fixtures" / "gleif" / "recorded.json").read_text(encoding="utf-8"))
VERVIERS, GROUP, BRAINE = "213800IK89OTMDYZTD06", "549300EFW4H2TCZ71055", "549300YE4PRLJJY2I238"


def transport(state=None):
    """state: an optional dict; state["down"] = True makes every call fail like an outage."""
    state = state if state is not None else {}

    def handler(request: httpx.Request) -> httpx.Response:
        if state.get("down"):
            raise httpx.ConnectError("GLEIF is down", request=request)
        path = request.url.path.removeprefix("/api/v1")
        if path == "/lei-records":
            q = request.url.params.get("filter[fulltext]", "")
            country = request.url.params.get("filter[entity.legalAddress.country]", "")
            body = RECORDED.get(f"/lei-records?country={country}&q={q}")
            return httpx.Response(200, json=body or {"data": [], "meta": {}})
        body = RECORDED.get(path)
        if body is None:
            return httpx.Response(404, json={"errors": [{"status": "404", "title": "Resource not found"}]})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)
