"""
SCIRM tenant context for internal services.

The API gateway is the only component that verifies user JWTs. It forwards the
caller's identity to internal services in headers, authenticated by a shared
service key. Internal services must take the organization from these headers
and never from request bodies or query parameters.

Deliberately dependency-light (no JWT / passlib) so every service can import it.
"""

import hmac
import os
from typing import Dict

from fastapi import HTTPException, Request, status

ORG_HEADER = "X-Org-Id"
USER_HEADER = "X-User-Id"
SERVICE_KEY_HEADER = "X-Service-Key"

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_IS_DEV = _ENVIRONMENT in {"development", "dev", "local", "test"}
_SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")

if not _SERVICE_API_KEY and not _IS_DEV:
    raise RuntimeError(f"SERVICE_API_KEY must be set when ENVIRONMENT={_ENVIRONMENT!r}.")


def internal_headers(org_id: str, user_id: str = "") -> Dict[str, str]:
    """Headers a caller attaches when invoking an internal service on behalf of a tenant."""
    headers = {ORG_HEADER: org_id}
    if user_id:
        headers[USER_HEADER] = user_id
    if _SERVICE_API_KEY:
        headers[SERVICE_KEY_HEADER] = _SERVICE_API_KEY
    return headers


def _check_service_key(request: Request) -> None:
    if not _SERVICE_API_KEY:
        return  # Development only — enforced at import time above
    key = request.headers.get(SERVICE_KEY_HEADER, "")
    if not key or not hmac.compare_digest(key.encode(), _SERVICE_API_KEY.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service key")


async def tenant_org(request: Request) -> str:
    """FastAPI dependency: authenticate the calling service and return the tenant org id."""
    _check_service_key(request)
    org_id = request.headers.get(ORG_HEADER, "").strip()
    if not org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Missing {ORG_HEADER} header")
    return org_id
