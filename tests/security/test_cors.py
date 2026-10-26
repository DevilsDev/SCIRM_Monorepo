"""
CORS for the web app (a different origin from the gateway): every method it uses must pass
the browser's preflight, and the headers it reads must be exposed.
"""

ORIGIN = "http://localhost:3000"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_preflight_allows_the_supplier_portal_token(client):
    """Found in the live check: the portal's X-Portal-Token header failed the preflight."""
    for method in ("GET", "PUT", "POST"):
        response = client.options("/api/v1/portal/assessment", headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type,x-portal-token"})
        assert response.status_code == 200, (method, response.text)
        assert "x-portal-token" in response.headers["access-control-allow-headers"].lower()


def test_preflight_allows_every_method_the_app_uses(client):
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        response = client.options("/api/v1/org/members/x", headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type"})
        assert response.status_code == 200, (method, response.text)
        assert method in response.headers["access-control-allow-methods"]


def test_unknown_origins_are_not_allowed(client):
    response = client.options("/api/v1/suppliers", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in response.headers


def test_the_audit_export_headers_are_readable_by_the_app(client, sarah):
    response = client.get("/api/v1/audit/export", headers={**bearer(sarah["access_token"]), "Origin": ORIGIN})
    exposed = response.headers.get("access-control-expose-headers", "").lower()
    assert "x-rows" in exposed and "x-truncated" in exposed
