"""
SCIRM API Gateway
Central entry point for all client requests, routing to appropriate agent services.
"""

import asyncio
import hmac
import json
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from urllib.parse import quote, urlencode
from uuid import uuid4

import httpx
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
import structlog

from libs.common.auth import (
    verify_token, decode_token, require_write_access, create_access_token,
    create_refresh_token, verify_password, get_password_hash, generate_totp_secret,
    get_totp_uri, verify_totp, MFA_ENABLED, IS_DEV, MAX_PASSWORD_BYTES,
    TOKEN_TYPE_ACCESS, TOKEN_TYPE_REFRESH, TOKEN_TYPE_MFA_PENDING,
)
from libs.common.monitoring import setup_monitoring
from libs.common.models import RiskAssessmentRequest, RiskAssessmentResponse
from libs.common.security import setup_cors, setup_rate_limiting
from libs.common.store import (API_KEY_PREFIX, AUDIT_CATEGORY_NAMES, FEEDBACK_VERDICTS, ROLES, EmailExists, LastAdmin,
                               audit_category, audit_cursor, create_store, is_api_key)
from libs.common import secret_box
from libs.integrations import reports, webhooks

# MFA seeds are encrypted at rest; outside development the key must be configured.
secret_box.require_key()
from libs.common.tenancy import internal_headers

logger = structlog.get_logger()

# Service URLs from environment
COORDINATOR_URL = os.getenv("COORDINATOR_SERVICE_URL", "http://localhost:8001")
PLANNER_URL = os.getenv("PLANNER_SERVICE_URL", "http://localhost:8002")
RESEARCHER_URL = os.getenv("RESEARCHER_SERVICE_URL", "http://localhost:8003")
EXECUTOR_URL = os.getenv("EXECUTOR_SERVICE_URL", "http://localhost:8004")
REVIEWER_URL = os.getenv("REVIEWER_SERVICE_URL", "http://localhost:8005")
RISK_SCORER_URL = os.getenv("RISK_SCORER_SERVICE_URL", "http://localhost:8006")
DISCOVERY_URL = os.getenv("DISCOVERY_SERVICE_URL", "http://localhost:8007")
INGESTION_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8008")
CHAT_URL = os.getenv("CHAT_SERVICE_URL", "http://localhost:8009")
SIMULATOR_URL = os.getenv("SIMULATOR_SERVICE_URL", "http://localhost:8010")
PROCUREMENT_URL = os.getenv("PROCUREMENT_SERVICE_URL", "http://localhost:8011")
COMPONENT_TRACKER_URL = os.getenv("COMPONENT_TRACKER_URL", "http://localhost:8012")

security = HTTPBearer()


def _svc_headers(user) -> Dict[str, str]:
    """Identity headers for internal services. The org always comes from the verified token."""
    return internal_headers(user.organization_id, user.id)

# Audit trail (and, later, other gateway-owned data). Memory in development/tests.
audit_store = create_store()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SCIRM API Gateway")
    yield
    await audit_store.close()
    logger.info("Shutting down SCIRM API Gateway")

app = FastAPI(
    title="SCIRM API Gateway",
    description="AI-Powered Supply Chain Risk Management Platform",
    version="1.0.0",
    lifespan=lifespan,
)

_AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Recorded by the handlers themselves, with the account email.
_SELF_AUDITED_PATHS = {"/api/v1/auth/login", "/api/v1/invitations/accept", "/api/v1/invitations/lookup"}


async def _account_owner(email: str) -> Optional[Dict[str, Any]]:
    """The organization and id of an existing account, so a failed sign-in on it shows in
    that organization's audit log. Unknown emails stay unattributed."""
    email = (email or "").strip().lower()
    demo = DEV_USERS.get(email)
    if demo:
        return {"org_id": demo["org_id"], "id": demo["id"]}
    try:
        row = await audit_store.find_login_user(email)
    except Exception:
        return None
    return {"org_id": str(row["organization_id"]), "id": str(row["id"])} if row else None


async def _audit_auth(action: str, email: str, user_info: Optional[Dict[str, Any]], ok: bool,
                      ip: Optional[str] = None) -> None:
    if not ok:
        user_info = await _account_owner(email)
    try:
        await audit_store.record_audit(user_info["org_id"] if user_info else None, {
            "user_id": user_info["id"] if user_info else None,
            "actor_type": "user",
            "actor": email,
            "action": action if ok else f"{action}_failed",
            "resource_type": "auth",
            "status_code": 200 if ok else 401,
            "ip_address": ip,
        })
    except Exception as exc:
        logger.error("Audit write failed", error=str(exc), action=action)


def _caller(request: Request) -> Dict[str, Any]:
    """Identity for the audit record, from the bearer token if it is valid."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            payload = decode_token(auth[7:], TOKEN_TYPE_ACCESS)
            return {"org": payload.get("org_id"), "user_id": payload.get("sub"), "actor": payload.get("email")}
        except HTTPException:
            pass
    return {"org": None, "user_id": None, "actor": None}


@app.middleware("http")
async def sample_features_gate(request: Request, call_next):
    """Refuse sample-data endpoints unless SAMPLE_FEATURES is on (see its definition)."""
    if not SAMPLE_FEATURES and _is_sample_feature(request.url.path):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "This feature is not available"})
    return await call_next(request)


@app.middleware("http")
async def audit_writes(request: Request, call_next):
    """Record every state-changing API call — who, which tenant, what, and the outcome."""
    response = await call_next(request)
    if (request.method in _AUDITED_METHODS and request.url.path.startswith("/api/v1/")
            and request.url.path not in _SELF_AUDITED_PATHS):
        caller = _caller(request)
        route = request.scope.get("route")
        template = getattr(route, "path", request.url.path)
        parts = request.url.path.split("/")  # ["", "api", "v1", resource, id, ...]
        params = request.scope.get("path_params", {})
        try:
            await audit_store.record_audit(caller["org"], {
                "user_id": caller["user_id"],
                "actor_type": "user" if caller["user_id"] else "anonymous",
                "actor": caller["actor"],
                "action": f"{request.method} {template}",
                "resource_type": parts[3] if len(parts) > 3 else "unknown",
                "resource_id": next(iter(params.values()), None),
                "status_code": response.status_code,
                "ip_address": request.client.host if request.client else None,
                "details": {"path": request.url.path},
            })
        except Exception as exc:  # never lose the error silently
            logger.error("Audit write failed", error=str(exc), path=request.url.path)
    return response


# The read-only public API: the only routes an API key can call, as exact (method, route
# template) pairs. Anything else (team, MFA, audit log, integrations, writes, ...) is refused.
API_KEY_ROUTES = frozenset({
    ("GET", "/api/v1/suppliers"),
    ("GET", "/api/v1/suppliers/{supplier_id}"),
    ("GET", "/api/v1/suppliers/{supplier_id}/signals"),
    ("GET", "/api/v1/signals/suppliers"),
    ("GET", "/api/v1/alerts"),
    ("GET", "/api/v1/risks"),
    ("GET", "/api/v1/risks/{risk_id}"),
    ("GET", "/api/v1/intelligence/feed"),
    ("GET", "/api/v1/intelligence/sources"),
    ("GET", "/api/v1/export/suppliers"),
})


def _presented_api_key(request: Request) -> Optional[str]:
    explicit = request.headers.get("x-api-key", "").strip()
    if explicit:
        return explicit
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and auth[7:].strip().startswith(API_KEY_PREFIX):
        return auth[7:].strip()
    return None


def _route_template(scope) -> Optional[str]:
    from starlette.routing import Match
    for route in app.router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "path", None)
    return None


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Accept an API key on the public API's routes only. It is swapped for a one-minute
    internal access token with the viewer role, so the handlers and their checks run
    unchanged; the key's id stands in for the user. Refusals are audited by prefix."""
    key = _presented_api_key(request)
    if key is None:
        return await call_next(request)
    from fastapi.responses import JSONResponse
    found = await audit_store.find_api_key(key) if is_api_key(key) else None
    template = _route_template(request.scope)

    async def refuse(status: int, detail: str):
        try:
            await audit_store.record_audit(found["organization_id"] if found else None, {
                "actor_type": "api_key", "actor": f"api-key:{key[:14]}", "action": "api_key.refused",
                "resource_type": "api_key", "resource_id": found["id"] if found else None, "status_code": status,
                "ip_address": request.client.host if request.client else None,
                "details": {"method": request.method, "path": request.url.path}})
        except Exception as exc:
            logger.error("Audit write failed", error=type(exc).__name__, action="api_key.refused")
        return JSONResponse(status_code=status, content={"detail": detail})

    if not found or not found.get("live"):
        return await refuse(401, "Invalid, expired or revoked API key")
    if (request.method, template) not in API_KEY_ROUTES:
        return await refuse(403, "API keys can only read suppliers, their public records, alerts, risks and the "
                                 "intelligence feed. See the API documentation.")
    token = create_access_token(data={
        "sub": str(found["id"]), "email": f"api-key:{found['name']} ({found['prefix']})", "name": found["name"],
        "roles": ["viewer"], "org_id": str(found["organization_id"]), "api_key": True,
    }, expires_delta=timedelta(minutes=1))
    request.scope["headers"] = [(k, v) for k, v in request.scope["headers"] if k not in (b"authorization", b"x-api-key")]
    request.scope["headers"].append((b"authorization", f"Bearer {token}".encode()))
    try:
        await audit_store.touch_api_key(str(found["organization_id"]), str(found["id"]))
    except Exception as exc:
        logger.warning("Could not record API key use", error=type(exc).__name__)
    return await call_next(request)


setup_cors(app)
setup_rate_limiting(app, requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "100")),
                    burst=int(os.getenv("RATE_LIMIT_BURST", "200")))
setup_monitoring(app, service_name="api-gateway")

class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]

class LoginRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    email: str
    password: str
    name: str
    organization_name: Optional[str] = Field(None, max_length=255)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    services = {}
    
    async with httpx.AsyncClient() as client:
        for service_name, url in [
            ("coordinator", COORDINATOR_URL),
            ("planner", PLANNER_URL),
            ("researcher", RESEARCHER_URL),
            ("executor", EXECUTOR_URL),
            ("reviewer", REVIEWER_URL),
        ]:
            try:
                response = await client.get(f"{url}/health", timeout=5.0)
                services[service_name] = "healthy" if response.status_code == 200 else "unhealthy"
            except Exception:
                services[service_name] = "unreachable"
    
    overall_status = "healthy" if all(status == "healthy" for status in services.values()) else "degraded"
    
    return HealthResponse(status=overall_status, services=services)

@app.get("/ready")
async def readiness():
    """Readiness probe for Kubernetes."""
    return {"status": "ready", "service": "api-gateway"}

# Built-in demo accounts exist only in development. Their shared password comes from
# DEV_PASSWORD, or is generated at startup and printed to the console — never hardcoded.
if IS_DEV:
    DEV_PASSWORD = os.getenv("DEV_PASSWORD") or secrets.token_urlsafe(12)
    if not os.getenv("DEV_PASSWORD"):
        print(f"[api-gateway] Dev login password for demo accounts: {DEV_PASSWORD}", flush=True)
    DEV_USERS = {
        "sarah.chen@pharmacorp.com": {"id": "b0000000-0000-0000-0000-000000000001", "name": "Sarah Chen", "roles": ["admin", "analyst"], "org_id": "a0000000-0000-0000-0000-000000000001", "mfa_secret": None},
        "marcus.rodriguez@pharmacorp.com": {"id": "b0000000-0000-0000-0000-000000000002", "name": "Marcus Rodriguez", "roles": ["analyst"], "org_id": "a0000000-0000-0000-0000-000000000001", "mfa_secret": None},
        "lisa.park@medtech.com": {"id": "b0000000-0000-0000-0000-000000000003", "name": "Lisa Park", "roles": ["admin", "analyst"], "org_id": "a0000000-0000-0000-0000-000000000002", "mfa_secret": None},
        "auditor@scirm.dev": {"id": "b0000000-0000-0000-0000-000000000004", "name": "SCIRM Auditor", "roles": ["auditor", "viewer"], "org_id": "a0000000-0000-0000-0000-000000000003", "mfa_secret": None},
    }
else:
    DEV_PASSWORD = None
    DEV_USERS = {}


# Self-service signup creates a new organization. Off outside development: customers are
# onboarded by an operator (scripts/create_tenant.py) and add teammates by invitation.
SIGNUP_MODE = os.getenv("SIGNUP_MODE", "open" if IS_DEV else "closed").lower()
# Features that run on built-in sample data or unvalidated formulas (scenario simulators,
# procurement alternatives, components and BOMs, 7-day "predictions", the rule-based risk
# score). On by default only in development and test; elsewhere their endpoints are
# refused, so a pilot never sees sample output presented as analysis.
SAMPLE_FEATURES = (os.getenv("SAMPLE_FEATURES") or ("true" if IS_DEV else "false")).lower() == "true"
SAMPLE_FEATURE_PATHS = ("/api/v1/predictions", "/api/v1/simulator", "/api/v1/scenarios", "/api/v1/procurement",
                        "/api/v1/components", "/api/v1/products", "/api/v1/risk-score", "/api/v1/risk-dimensions")


def _is_sample_feature(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in SAMPLE_FEATURE_PATHS)


# Base for invitation links. Configured, never taken from the request's Host header.
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:3000" if IS_DEV else "").rstrip("/")
# Checked for unknown emails too, so response time does not reveal which accounts exist.
_DUMMY_PASSWORD_HASH = get_password_hash(secrets.token_urlsafe(16))


def _account_info(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": str(row["id"]), "name": row["name"], "roles": list(row["roles"] or []),
            "org_id": str(row["organization_id"]), "mfa_secret": row.get("mfa_secret"),
            "mfa_enabled": bool(row.get("mfa_enabled")), "password_changed_at": row.get("password_changed_at"),
            "stored": True}


def _mfa_on(user_info: Dict[str, Any]) -> bool:
    """Confirmed two-step sign-in. A seed alone may be a pending enrollment nobody has
    confirmed, and must not lock its owner out."""
    return bool(user_info.get("mfa_secret")) and bool(user_info.get("mfa_enabled"))


async def _find_user_by_id(user_id: str) -> Optional[tuple]:
    """(email, info) for an active account, from the demo accounts (development) or the database."""
    for email, info in DEV_USERS.items():
        if info["id"] == user_id:
            return email, info
    row = await audit_store.get_user_by_id(user_id)
    if row and row["is_active"]:
        return row["email"], _account_info(row)
    return None


async def _check_password(email: str, password: str) -> Optional[Dict[str, Any]]:
    email = (email or "").strip().lower()
    dev_user = DEV_USERS.get(email)
    if dev_user:
        ok = bool(DEV_PASSWORD) and hmac.compare_digest(password.encode(), DEV_PASSWORD.encode())
        return dev_user if ok else None
    row = await audit_store.find_login_user(email)
    if not row:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, row["hashed_password"]) or not row["is_active"]:
        return None
    return _account_info(row)


def _issue_tokens(email: str, user_info: Dict[str, Any]) -> Dict[str, str]:
    token = create_access_token(data={
        "sub": user_info["id"],
        "email": email,
        "name": user_info["name"],
        "roles": user_info["roles"],
        "org_id": user_info["org_id"],
    })
    refresh = create_refresh_token(user_info["id"])
    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer"}


class MFAVerifyRequest(BaseModel):
    totp_code: str
    mfa_token: str


@app.get("/api/v1/config")
async def client_config(token: str = Depends(security)):
    """What the web app should show for this deployment."""
    await verify_token(token.credentials)
    return {"features": {"sample_pages": SAMPLE_FEATURES}}


@app.post("/api/v1/auth/login")
async def login(request: LoginRequest, http_request: Request):
    """Authenticate user. If MFA is enabled, returns mfa_required=true with a temporary token."""
    user_info = await _check_password(request.email, request.password)
    # Record the attempt with the email (never the password); the middleware cannot read bodies.
    await _audit_auth("auth.login", request.email, user_info, ok=bool(user_info),
                      ip=http_request.client.host if http_request.client else None)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if MFA is required
    if MFA_ENABLED and _mfa_on(user_info):
        mfa_token = create_access_token(
            data={"sub": user_info["id"], "type": TOKEN_TYPE_MFA_PENDING, "email": request.email.strip().lower()},
            expires_delta=timedelta(minutes=5),
        )
        return {"mfa_required": True, "mfa_token": mfa_token, "token_type": "bearer"}

    await _record_login(user_info)
    return _issue_tokens(request.email.strip().lower(), user_info)


async def _record_login(user_info: Dict[str, Any]) -> None:
    if user_info.get("stored"):
        try:
            await audit_store.record_login(user_info["org_id"], user_info["id"])
        except Exception as exc:
            logger.warning("Could not record login time", error=type(exc).__name__)


@app.post("/api/v1/auth/mfa/verify")
async def verify_mfa(request: MFAVerifyRequest):
    """Verify TOTP code after initial login when MFA is enabled.

    The mfa_token proves the password step succeeded; the user is taken from it,
    never from the request body.
    """
    payload = decode_token(request.mfa_token, TOKEN_TYPE_MFA_PENDING)
    found = await _find_user_by_id(payload["sub"])
    if not found or found[0] != (payload.get("email") or "").lower():
        raise HTTPException(status_code=401, detail="Invalid MFA token")
    email, user_info = found
    if not _mfa_on(user_info):
        raise HTTPException(status_code=400, detail="MFA not configured for this user")

    if not verify_totp(user_info["mfa_secret"], request.totp_code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")

    await _record_login(user_info)
    return _issue_tokens(email, user_info)


class MFACodeRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=8)


async def _save_mfa(org: str, user_id: str, email: str, secret: Optional[str], enabled: bool) -> None:
    # Demo accounts (development only) keep it in memory; real accounts store it encrypted
    # (libs/common/secret_box.py, applied by the store).
    demo = DEV_USERS.get(email.lower())
    if demo and demo["id"] == user_id:
        demo.update(mfa_secret=secret, mfa_enabled=bool(secret) and enabled)
    elif not await audit_store.set_mfa_secret(org, user_id, secret, enabled):
        raise HTTPException(status_code=404, detail="Account not found")


async def _audit_event(org: str, user_id: str, actor: str, action: str, target: Optional[str] = None) -> None:
    try:
        await audit_store.record_audit(org, {
            "user_id": user_id, "actor_type": "user", "actor": actor, "action": action,
            "resource_type": "auth", "resource_id": target, "status_code": 200})
    except Exception as exc:
        logger.error("Audit write failed", error=type(exc).__name__, action=action)


async def _own_account(token: str) -> tuple:
    user = await verify_token(token)
    found = await _find_user_by_id(user.id)
    if not found:
        raise HTTPException(status_code=404, detail="Account not found")
    return user, found[1]


@app.get("/api/v1/auth/mfa")
async def mfa_status(token: str = Depends(security)):
    """Whether the caller has two-step sign-in on, and whether this deployment asks for it."""
    _, info = await _own_account(token.credentials)
    return {"enabled": _mfa_on(info), "pending": bool(info.get("mfa_secret")) and not _mfa_on(info),
            "enforced_at_sign_in": MFA_ENABLED}


@app.post("/api/v1/auth/mfa/setup")
async def setup_mfa(token: str = Depends(security)):
    """Start enrollment: a new TOTP seed, stored as pending. Sign-in does not ask for codes
    until /mfa/confirm proves the authenticator works. Refused while two-step sign-in is on,
    so a stolen session cannot swap in another authenticator; turn it off first (needs a code)."""
    user, info = await _own_account(token.credentials)
    if _mfa_on(info):
        raise HTTPException(status_code=409, detail="Two-step sign-in is already on. Turn it off first.")
    secret = generate_totp_secret()
    await _save_mfa(user.organization_id, user.id, user.email, secret, enabled=False)
    return {"secret": secret, "otpauth_uri": get_totp_uri(secret, user.email),
            "message": "Add this key to your authenticator app, then confirm with a code from it."}


@app.post("/api/v1/auth/mfa/confirm")
async def confirm_mfa(body: MFACodeRequest, token: str = Depends(security)):
    """Finish enrollment with a current code from the authenticator."""
    user, info = await _own_account(token.credentials)
    if _mfa_on(info):
        return {"enabled": True}
    if not info.get("mfa_secret"):
        raise HTTPException(status_code=400, detail="Start setup first")
    if not verify_totp(info["mfa_secret"], body.totp_code):
        raise HTTPException(status_code=400, detail="That code is not valid. Check the time on your device and try again.")
    await _save_mfa(user.organization_id, user.id, user.email, info["mfa_secret"], enabled=True)
    await _audit_event(user.organization_id, user.id, user.email, "mfa.enabled")
    return {"enabled": True}


@app.post("/api/v1/auth/mfa/disable")
async def disable_mfa(body: MFACodeRequest, token: str = Depends(security)):
    """Turn two-step sign-in off. Needs a current code, so a stolen session alone cannot."""
    user, info = await _own_account(token.credentials)
    if not _mfa_on(info):
        await _save_mfa(user.organization_id, user.id, user.email, None, enabled=False)  # drop a pending seed
        return {"enabled": False}
    if not verify_totp(info["mfa_secret"], body.totp_code):
        raise HTTPException(status_code=400, detail="That code is not valid.")
    await _save_mfa(user.organization_id, user.id, user.email, None, enabled=False)
    await _audit_event(user.organization_id, user.id, user.email, "mfa.disabled")
    return {"enabled": False}


def _issued_before_password_change(payload: Dict[str, Any], info: Dict[str, Any]) -> bool:
    """A token issued before the account's last password change (change or reset)."""
    changed = info.get("password_changed_at")
    if not changed or "iat" not in payload:
        return False
    changed_at = datetime.fromisoformat(str(changed))
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    return int(payload["iat"]) < int(changed_at.timestamp())


@app.post("/api/v1/auth/refresh")
async def refresh_token(body: Dict[str, Any]):
    """Exchange a refresh token for a new access token."""
    refresh = body.get("refresh_token", "")
    if not refresh:
        raise HTTPException(status_code=400, detail="refresh_token required")

    payload = decode_token(refresh, TOKEN_TYPE_REFRESH)
    found = await _find_user_by_id(payload["sub"])
    if not found:  # unknown, or deactivated since the refresh token was issued
        raise HTTPException(status_code=401, detail="User not found")
    if _issued_before_password_change(payload, found[1]):
        raise HTTPException(status_code=401, detail="The password was changed: sign in again")

    tokens = _issue_tokens(*found)
    return {"access_token": tokens["access_token"], "token_type": "bearer"}


# ---------------------------------------------------------------------------
# Team: members and invitations (tenant onboarding)
# ---------------------------------------------------------------------------

class InviteRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    roles: List[str] = Field(default_factory=lambda: ["analyst"], min_length=1, max_length=4)


class MemberUpdate(BaseModel):
    roles: Optional[List[str]] = Field(None, min_length=1, max_length=4)
    is_active: Optional[bool] = None


class InvitationTokenBody(BaseModel):
    # The token travels in the request body, never the URL: request paths are written to
    # the append-only audit log and to access logs.
    token: str = Field(..., min_length=20, max_length=200)


class AcceptInvitationRequest(InvitationTokenBody):
    name: str = Field(..., min_length=1, max_length=255)
    password: str


def _require_admin(user, what: str = "manage the team") -> None:
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail=f"Only administrators can {what}")


def _valid_roles(roles: List[str]) -> List[str]:
    roles = list(dict.fromkeys(r.strip().lower() for r in roles))
    unknown = [r for r in roles if r not in ROLES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown role(s): {', '.join(unknown)}. Allowed: {', '.join(ROLES)}")
    return roles


def _valid_email(email: str) -> str:
    email = email.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    return email


def _password_ok(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=400, detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes")


@app.get("/api/v1/org/members")
async def list_members(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    members = await audit_store.list_members(user.organization_id)
    # Development only: the built-in demo accounts are not stored, so list them read-only.
    demo = [{"id": info["id"], "email": email, "name": info["name"], "roles": info["roles"], "is_active": True,
             "mfa_enabled": _mfa_on(info), "created_at": None, "last_login_at": None, "demo": True}
            for email, info in DEV_USERS.items() if info["org_id"] == user.organization_id]
    return {"members": demo + members}


@app.patch("/api/v1/org/members/{member_id}")
async def update_member(member_id: str, body: MemberUpdate, token: str = Depends(security)):
    """Change a member's roles or deactivate them. Deactivation takes effect at their next
    token refresh (access tokens are not revoked early)."""
    user = await verify_token(token.credentials)
    _require_admin(user)
    if member_id == user.id and body.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    roles = _valid_roles(body.roles) if body.roles is not None else None
    try:
        member = await audit_store.update_member(user.organization_id, member_id, roles=roles, is_active=body.is_active)
    except LastAdmin:
        raise HTTPException(status_code=409, detail="The organization must keep at least one active administrator")
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@app.post("/api/v1/org/members/{member_id}/mfa/reset")
async def reset_member_mfa(member_id: str, token: str = Depends(security)):
    """Admin: turn off a teammate's two-step sign-in, e.g. after a lost phone, so they can
    sign in with their password and set it up again. Not for one's own account: that needs
    a current code (/auth/mfa/disable), so a stolen admin session cannot remove it."""
    user = await verify_token(token.credentials)
    _require_admin(user, "reset two-step sign-in")
    if member_id == user.id:
        raise HTTPException(status_code=400, detail="Turn off your own two-step sign-in in your settings, with a code.")
    demo = next((i for i in DEV_USERS.values() if i["id"] == member_id and i["org_id"] == user.organization_id), None)
    if demo:
        demo.update(mfa_secret=None, mfa_enabled=False)
    elif not await audit_store.set_mfa_secret(user.organization_id, member_id, None, False):
        raise HTTPException(status_code=404, detail="Member not found")
    await _audit_event(user.organization_id, user.id, user.email, "mfa.reset_by_admin", target=member_id)
    return {"reset": True}


class ApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: Optional[int] = Field(None, ge=1, le=730)


@app.get("/api/v1/org/api-keys")
async def list_api_keys(token: str = Depends(security)):
    """The organization's API keys (prefix only; a key is shown once, when created)."""
    user = await verify_token(token.credentials)
    _require_admin(user, "manage API keys")
    return {"api_keys": await audit_store.list_api_keys(user.organization_id)}


@app.post("/api/v1/org/api-keys")
async def create_api_key(body: ApiKeyRequest, token: str = Depends(security)):
    """A read-only key for the public API. Returns the key once; only its hash is stored."""
    user = await verify_token(token.credentials)
    _require_admin(user, "manage API keys")
    expires = (datetime.utcnow() + timedelta(days=body.expires_in_days)).isoformat() if body.expires_in_days else None
    row, key = await audit_store.create_api_key(user.organization_id, body.name.strip(), user.email, expires)
    await _audit_event(user.organization_id, user.id, user.email, "api_key.created", target=str(row["id"]))
    return {"api_key": row, "key": key,
            "note": "Copy this key now: it cannot be shown again. Send it as 'Authorization: Bearer <key>'."}


@app.delete("/api/v1/org/api-keys/{key_id}")
async def revoke_api_key(key_id: str, token: str = Depends(security)):
    """Revoke a key. Requests with it fail from the next one on."""
    user = await verify_token(token.credentials)
    _require_admin(user, "manage API keys")
    row = await audit_store.revoke_api_key(user.organization_id, key_id)
    if not row:
        raise HTTPException(status_code=404, detail="No active API key with that id")
    await _audit_event(user.organization_id, user.id, user.email, "api_key.revoked", target=key_id)
    return {"api_key": row}


class WebhookRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    description: Optional[str] = Field(None, max_length=200)
    events: List[str] = Field(default_factory=lambda: list(webhooks.EVENT_TYPES), min_length=1, max_length=2)


class WebhookUpdate(BaseModel):
    active: Optional[bool] = None
    events: Optional[List[str]] = Field(None, min_length=1, max_length=2)


def _webhook_events(events: List[str]) -> List[str]:
    events = list(dict.fromkeys(events))
    unknown = [e for e in events if e not in webhooks.EVENT_TYPES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown event(s): {', '.join(unknown)}. "
                                                    f"Allowed: {', '.join(webhooks.EVENT_TYPES)}")
    return events


@app.get("/api/v1/org/webhooks")
async def list_webhooks(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user, "manage webhooks")
    return {"webhooks": await audit_store.list_webhooks(user.organization_id), "event_types": list(webhooks.EVENT_TYPES)}


@app.post("/api/v1/org/webhooks")
async def create_webhook(body: WebhookRequest, token: str = Depends(security)):
    """Add an endpoint. Returns the signing secret once; it is stored encrypted."""
    user = await verify_token(token.credentials)
    _require_admin(user, "manage webhooks")
    try:
        url = webhooks.validate_url(body.url)
    except webhooks.WebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    secret = webhooks.new_secret()
    row = await audit_store.create_webhook(user.organization_id, url, (body.description or "").strip() or None,
                                           _webhook_events(body.events), secret, user.email)
    await _audit_event(user.organization_id, user.id, user.email, "webhook.created", target=str(row["id"]))
    return {"webhook": row, "secret": secret,
            "note": "Copy the signing secret now: it cannot be shown again. Use it to verify SCIRM-Signature."}


@app.patch("/api/v1/org/webhooks/{webhook_id}")
async def update_webhook(webhook_id: str, body: WebhookUpdate, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user, "manage webhooks")
    events = _webhook_events(body.events) if body.events is not None else None
    row = await audit_store.update_webhook(user.organization_id, webhook_id, active=body.active, events=events)
    if not row:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"webhook": row}


@app.delete("/api/v1/org/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user, "manage webhooks")
    if not await audit_store.delete_webhook(user.organization_id, webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    await _audit_event(user.organization_id, user.id, user.email, "webhook.deleted", target=webhook_id)
    return {"deleted": True}


@app.post("/api/v1/org/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str, token: str = Depends(security)):
    """Send a signed ping event to this endpoint now and report what it answered."""
    user = await verify_token(token.credentials)
    _require_admin(user, "manage webhooks")
    if not any(w["id"] == webhook_id for w in await audit_store.list_webhooks(user.organization_id)):
        raise HTTPException(status_code=404, detail="Webhook not found")
    event_ids = await audit_store.record_events(user.organization_id, [(
        "ping", f"ping:{uuid.uuid4()}", {"message": "Test event from SCIRM", "sent_by": user.email})],
        only_webhook=webhook_id)
    results = await webhooks.deliver_due(audit_store, user.organization_id, only_events=event_ids)
    if not results:
        raise HTTPException(status_code=409, detail="The webhook is paused. Resume it to send a test.")
    r = results[0]
    return {"ok": r["ok"], "status_code": r["status_code"], "error": r["error"], "event_id": r["event_id"]}


@app.get("/api/v1/org/webhooks/{webhook_id}/deliveries")
async def list_webhook_deliveries(webhook_id: str, limit: int = 20, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user, "manage webhooks")
    return {"deliveries": await audit_store.list_webhook_deliveries(user.organization_id, webhook_id,
                                                                    limit=min(max(limit, 1), 100))}


class ReportScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    frequency: str
    hour_utc: int = Field(..., ge=0, le=23)
    weekday: Optional[int] = Field(None, ge=0, le=6)
    recipients: List[str] = Field(..., min_length=1, max_length=20)
    skip_empty: bool = False


class ReportScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    frequency: Optional[str] = None
    hour_utc: Optional[int] = Field(None, ge=0, le=23)
    weekday: Optional[int] = Field(None, ge=0, le=6)
    recipients: Optional[List[str]] = Field(None, min_length=1, max_length=20)
    skip_empty: Optional[bool] = None
    active: Optional[bool] = None


async def _member_emails(org: str) -> set:
    emails = {m["email"].lower() for m in await audit_store.list_members(org) if m.get("is_active")}
    return emails | {email for email, info in DEV_USERS.items() if info["org_id"] == org}


async def _valid_recipients(org: str, recipients: List[str]) -> List[str]:
    """Only active members of the organization: a schedule must not mail supplier data out."""
    wanted = list(dict.fromkeys(r.strip().lower() for r in recipients if r.strip()))
    outside = [r for r in wanted if r not in await _member_emails(org)]
    if not wanted or outside:
        raise HTTPException(status_code=400, detail="Reports can only go to members of your organization"
                            + (f": not a member: {', '.join(outside)}" if outside else ""))
    return wanted


def _schedule_timing(frequency: str, hour_utc: int, weekday: Optional[int]) -> Dict[str, Any]:
    if frequency not in reports.FREQUENCIES:
        raise HTTPException(status_code=400, detail=f"frequency must be one of: {', '.join(reports.FREQUENCIES)}")
    if frequency == "weekly" and weekday is None:
        raise HTTPException(status_code=400, detail="A weekly report needs a weekday (0 = Monday)")
    weekday = weekday if frequency == "weekly" else None
    nxt = reports.next_run(frequency, hour_utc, weekday, datetime.now(timezone.utc))
    return {"frequency": frequency, "hour_utc": hour_utc, "weekday": weekday, "next_run_at": nxt.isoformat()}


def _schedule_view(row: Dict[str, Any]) -> Dict[str, Any]:
    return {**row, "when": reports.describe(row["frequency"], row["hour_utc"], row.get("weekday"))}


@app.get("/api/v1/org/reports")
async def list_report_schedules(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user, "manage scheduled reports")
    rows = await audit_store.list_report_schedules(user.organization_id)
    return {"schedules": [_schedule_view(r) for r in rows], "email_configured": reports.smtp_config() is not None,
            "members": sorted(await _member_emails(user.organization_id))}


@app.post("/api/v1/org/reports")
async def create_report_schedule(body: ReportScheduleRequest, token: str = Depends(security)):
    """A supplier risk digest emailed to members on a schedule (times in UTC)."""
    user = await verify_token(token.credentials)
    _require_admin(user, "manage scheduled reports")
    fields = {"name": body.name.strip(), "skip_empty": body.skip_empty,
              "recipients": await _valid_recipients(user.organization_id, body.recipients),
              **_schedule_timing(body.frequency, body.hour_utc, body.weekday)}
    row = await audit_store.create_report_schedule(user.organization_id, fields, user.email)
    await _audit_event(user.organization_id, user.id, user.email, "report.scheduled", target=str(row["id"]))
    return {"schedule": _schedule_view(row)}


@app.patch("/api/v1/org/reports/{schedule_id}")
async def update_report_schedule(schedule_id: str, body: ReportScheduleUpdate, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user, "manage scheduled reports")
    current = next((s for s in await audit_store.list_report_schedules(user.organization_id) if s["id"] == schedule_id),
                   None)
    if not current:
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    fields: Dict[str, Any] = {k: v for k, v in body.model_dump(exclude_unset=True).items()
                              if k in ("name", "skip_empty", "active") and v is not None}
    if body.recipients is not None:
        fields["recipients"] = await _valid_recipients(user.organization_id, body.recipients)
    if {"frequency", "hour_utc", "weekday"} & body.model_fields_set:
        fields.update(_schedule_timing(body.frequency or current["frequency"],
                                       body.hour_utc if body.hour_utc is not None else current["hour_utc"],
                                       body.weekday if "weekday" in body.model_fields_set else current.get("weekday")))
    elif fields.get("active"):  # resumed: next occurrence from now, not a missed one in the past
        fields["next_run_at"] = reports.next_run(current["frequency"], current["hour_utc"], current.get("weekday"),
                                                 datetime.now(timezone.utc)).isoformat()
    row = await audit_store.update_report_schedule(user.organization_id, schedule_id, fields)
    return {"schedule": _schedule_view(row)}


@app.delete("/api/v1/org/reports/{schedule_id}")
async def delete_report_schedule(schedule_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user, "manage scheduled reports")
    if not await audit_store.delete_report_schedule(user.organization_id, schedule_id):
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    await _audit_event(user.organization_id, user.id, user.email, "report.deleted", target=schedule_id)
    return {"deleted": True}


@app.post("/api/v1/org/reports/{schedule_id}/send-now")
async def send_report_now(schedule_id: str, token: str = Depends(security)):
    """Queue this report for the next pass (within about a minute). Its regular schedule
    continues afterwards."""
    user = await verify_token(token.credentials)
    _require_admin(user, "manage scheduled reports")
    if reports.smtp_config() is None:
        raise HTTPException(status_code=409, detail="Email is not configured on this deployment (SMTP_HOST).")
    row = await audit_store.update_report_schedule(user.organization_id, schedule_id,
                                                   {"next_run_at": await audit_store.db_now(), "active": True})
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    return {"schedule": _schedule_view(row), "note": "Queued: it is sent within about a minute."}


@app.post("/api/v1/org/invitations")
async def create_invitation(body: InviteRequest, token: str = Depends(security)):
    """Invite someone to this organization. Returns the invitation link once. There is no
    email service yet, so the administrator shares it. Treat it as a credential."""
    user = await verify_token(token.credentials)
    _require_admin(user)
    email = _valid_email(body.email)
    roles = _valid_roles(body.roles)
    if DEV_USERS.get(email):
        raise HTTPException(status_code=409, detail="That email already has an account")
    try:
        invitation, invite_token = await audit_store.create_invitation(user.organization_id, email, roles, user.id)
    except EmailExists:
        raise HTTPException(status_code=409, detail="That email already has an account")
    link = f"{PUBLIC_APP_URL}/invite#{invite_token}" if PUBLIC_APP_URL else f"/invite#{invite_token}"
    return {"invitation": invitation, "invite_url": link,
            "note": "Share this link with the invitee only. It works once and expires; it cannot be shown again."}


@app.get("/api/v1/org/invitations")
async def list_invitations(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user)
    return {"invitations": await audit_store.list_invitations(user.organization_id)}


@app.delete("/api/v1/org/invitations/{invitation_id}")
async def revoke_invitation(invitation_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    _require_admin(user)
    if not await audit_store.revoke_invitation(user.organization_id, invitation_id):
        raise HTTPException(status_code=404, detail="No pending invitation with that id")
    return {"revoked": True}


@app.post("/api/v1/invitations/lookup")
async def lookup_invitation(body: InvitationTokenBody):
    """Public: what an invitation link is for, so the invitee can confirm before joining."""
    invitation = await audit_store.lookup_invitation(body.token)
    if not invitation:  # unknown, used, revoked and expired all look the same
        raise HTTPException(status_code=404, detail="This invitation is not valid. Ask for a new one.")
    return {k: invitation[k] for k in ("organization_name", "email", "roles", "expires_at")}


@app.post("/api/v1/invitations/accept")
async def accept_invitation(body: AcceptInvitationRequest):
    """Public: create the account an invitation is for, and sign in. The email and
    organization come from the invitation, never from the request."""
    _password_ok(body.password)
    try:
        accepted = await audit_store.accept_invitation(body.token, body.name.strip(), get_password_hash(body.password))
    except EmailExists:
        raise HTTPException(status_code=409, detail="That email already has an account. Sign in instead.")
    if not accepted:
        raise HTTPException(status_code=404, detail="This invitation is not valid. Ask for a new one.")
    user_info = {"id": str(accepted["user_id"]), "name": body.name.strip(), "roles": list(accepted["roles"]),
                 "org_id": str(accepted["organization_id"]), "stored": True}
    await _record_login(user_info)  # accepting signs them in
    try:
        await audit_store.record_audit(user_info["org_id"], {
            "user_id": user_info["id"], "actor_type": "user", "actor": accepted["email"],
            "action": "invitation.accepted", "resource_type": "auth", "status_code": 200})
    except Exception as exc:
        logger.error("Audit write failed", error=type(exc).__name__, action="invitation.accepted")
    return _issue_tokens(accepted["email"], user_info)


OAUTH_PROVIDERS = {
    "google": "https://accounts.google.com/o/oauth2/v2/auth",
    "azure": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
}


@app.get("/api/v1/auth/oauth/authorize")
async def oauth_authorize(provider: str = "google", redirect_uri: str = "http://localhost:3000/auth/callback"):
    """
    OAuth 2.0 authorization endpoint — returns the provider's auth URL.
    In production, this redirects to the actual OAuth provider.
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")
    allowed_redirects = [o.rstrip("/") + "/auth/callback" for o in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
    if redirect_uri not in allowed_redirects:
        raise HTTPException(status_code=400, detail="redirect_uri not allowed")

    state = secrets.token_urlsafe(32)
    query = urlencode({
        "client_id": "scirm",
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    })
    return {
        "provider": provider,
        "authorization_url": f"{OAUTH_PROVIDERS[provider]}?{query}",
        "state": state,
        "message": "OAuth provider integration — redirect user to authorization_url",
    }


@app.post("/api/v1/auth/signup")
async def signup(request: SignupRequest):
    """Register a new user account.

    Each signup gets its own new organization. Joining an existing organization
    must go through an invitation flow, never a client-supplied organization_id.
    """
    if SIGNUP_MODE != "open":
        raise HTTPException(status_code=403, detail="Sign-up is by invitation. Ask your organization's administrator.")
    email = request.email.strip().lower()
    if DEV_USERS.get(email) or await audit_store.find_login_user(email):
        raise HTTPException(status_code=409, detail="Email already registered")

    # Validate password strength
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if len(request.password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=400, detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes")

    org_id = await audit_store.create_organization(
        (request.organization_name or f"{request.name}'s organization").strip()[:255])
    try:
        member = await audit_store.create_user(org_id, email, request.name, get_password_hash(request.password),
                                               ["admin", "analyst"])  # owner of the new organization
    except EmailExists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user_id = member["id"]
    user_info = {"id": user_id, "name": request.name, "roles": member["roles"], "org_id": org_id}

    logger.info("User registered", user_id=user_id)

    return {
        **_issue_tokens(email, user_info),
        "user": {
            "id": user_id,
            "email": request.email,
            "name": request.name,
            "roles": user_info["roles"],
        },
    }


@app.post("/api/v1/risk-assessment", response_model=RiskAssessmentResponse)
async def assess_risk(
    request: RiskAssessmentRequest,
    token: str = Depends(security)
):
    """Initiate risk assessment through coordinator agent."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{COORDINATOR_URL}/assess-risk",
                json=request.model_dump(mode="json"),
                headers=_svc_headers(user),
                timeout=30.0
            )
            response.raise_for_status()
            result = RiskAssessmentResponse(**response.json())

            # Broadcast real-time events to WebSocket clients
            await manager.broadcast(user.organization_id, {
                "event": "risk_update",
                "data": {
                    "task_id": result.task_id,
                    "risks_count": len(result.risks),
                    "recommendations_count": len(result.recommendations),
                    "confidence_score": result.confidence_score,
                },
            })
            for risk in result.risks:
                sev = risk.severity if hasattr(risk, 'severity') else risk.get("severity", "")
                if sev in ("high", "critical"):
                    await manager.broadcast(user.organization_id, {
                        "event": "alert_triggered",
                        "data": {
                            "severity": sev,
                            "title": risk.title if hasattr(risk, 'title') else risk.get("title", ""),
                            "risk_id": risk.id if hasattr(risk, 'id') else risk.get("id", ""),
                        },
                    })

            return result

    except httpx.HTTPError as e:
        logger.error("Risk assessment failed", error=str(e))
        raise HTTPException(status_code=500, detail="Risk assessment service unavailable")

@app.get("/api/v1/risks")
async def get_risks(
    limit: int = 50,
    offset: int = 0,
    severity: str = None,
    token: str = Depends(security)
):
    """Get current risk alerts."""
    user = await verify_token(token.credentials)
    
    try:
        async with httpx.AsyncClient() as client:
            params = {"limit": limit, "offset": offset}
            if severity:
                params["severity"] = severity
                
            response = await client.get(
                f"{COORDINATOR_URL}/risks",
                params=params,
                headers=_svc_headers(user),
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    except httpx.HTTPError as e:
        logger.error("Failed to fetch risks", error=str(e))
        raise HTTPException(status_code=500, detail="Risk service unavailable")

# --- Risk History ---

@app.get("/api/v1/risks/history")
async def risk_history(limit: int = 100, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/risks/history", params={"limit": limit}, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch risk history", error=str(e))
        raise HTTPException(status_code=500, detail="Risk history unavailable")

@app.get("/api/v1/risks/{risk_id}")
async def get_risk(
    risk_id: str,
    token: str = Depends(security)
):
    """Get a single risk by ID."""
    user = await verify_token(token.credentials)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{COORDINATOR_URL}/risks/{quote(risk_id, safe='')}",
                headers=_svc_headers(user),
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        logger.error("Failed to fetch risk", risk_id=risk_id, error=str(e))
        raise HTTPException(status_code=404, detail="Risk not found")

@app.get("/api/v1/recommendations/{risk_id}")
async def get_recommendations(
    risk_id: str,
    token: str = Depends(security)
):
    """Get mitigation recommendations for a specific risk."""
    user = await verify_token(token.credentials)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{COORDINATOR_URL}/recommendations/{quote(risk_id, safe='')}",
                headers=_svc_headers(user),
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    except httpx.HTTPError as e:
        logger.error("Failed to fetch recommendations", risk_id=risk_id, error=str(e))
        raise HTTPException(status_code=500, detail="Recommendation service unavailable")

# --- Suppliers ---

@app.get("/api/v1/suppliers")
async def list_suppliers(
    risk_tier: str = None, limit: int = 50,
    token: str = Depends(security),
):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {"limit": limit}
            if risk_tier:
                params["risk_tier"] = risk_tier
            response = await client.get(f"{COORDINATOR_URL}/suppliers", params=params, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch suppliers", error=str(e))
        raise HTTPException(status_code=500, detail="Supplier service unavailable")

@app.get("/api/v1/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/suppliers/{quote(supplier_id, safe='')}", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=404, detail="Supplier not found")

async def _coordinator_get(user: dict, path: str, params: dict, failure: str):
    """GET from the coordinator, passing 404 and 503 through so callers can tell
    "no such supplier" from "signals temporarily unavailable"."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}{path}", params={k: v for k, v in params.items() if v is not None},
                                        headers=_svc_headers(user), timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 503):
            raise HTTPException(status_code=e.response.status_code, detail=e.response.json().get("detail", failure))
        raise HTTPException(status_code=502, detail=failure)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail=failure)


@app.get("/api/v1/suppliers/{supplier_id}/signals")
async def supplier_signals(supplier_id: str, since_days: int = None, min_confidence: float = None,
                           token: str = Depends(security)):
    """Public records (FDA recalls and shortages, disaster alerts) concerning one supplier."""
    user = await verify_token(token.credentials)
    return await _coordinator_get(user, f"/suppliers/{quote(supplier_id, safe='')}/signals",
                                  {"since_days": since_days, "min_confidence": min_confidence},
                                  "Supplier signals unavailable")


class SiteBody(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., pattern=r"^[A-Za-z]{2}$")
    city: Optional[str] = Field(None, max_length=100)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)


async def _coordinator_write(user, method: str, path: str, body: Optional[Dict[str, Any]] = None):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(method, f"{COORDINATOR_URL}{path}", json=body,
                                             headers=_svc_headers(user), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404):
            raise HTTPException(status_code=e.response.status_code, detail=e.response.json().get("detail"))
        if e.response.status_code == 422:
            raise HTTPException(status_code=400, detail="Invalid site")
        raise HTTPException(status_code=502, detail="Supplier service failed")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Supplier service unavailable")


@app.post("/api/v1/suppliers/{supplier_id}/sites")
async def add_supplier_site(supplier_id: str, body: SiteBody, token: str = Depends(security)):
    """Add a place the supplier operates (city, or exact coordinates), for site-level disaster exposure."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    return await _coordinator_write(user, "POST", f"/suppliers/{quote(supplier_id, safe='')}/sites", body.model_dump())


@app.delete("/api/v1/suppliers/{supplier_id}/sites/{site_id}")
async def remove_supplier_site(supplier_id: str, site_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    require_write_access(user)
    return await _coordinator_write(user, "DELETE",
                                    f"/suppliers/{quote(supplier_id, safe='')}/sites/{quote(site_id, safe='')}")


class SupplierQuestion(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@app.post("/api/v1/suppliers/{supplier_id}/ask")
async def ask_about_supplier(supplier_id: str, body: SupplierQuestion, token: str = Depends(security)):
    """Grounded answer from public records about one supplier; every sentence cites a record."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/suppliers/{quote(supplier_id, safe='')}/ask",
                                         json=body.model_dump(), headers=_svc_headers(user), timeout=60.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 503):
            raise HTTPException(status_code=e.response.status_code, detail=e.response.json().get("detail"))
        raise HTTPException(status_code=502, detail="Answering failed")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Answering is unavailable")


class ScanUpload(BaseModel):
    csv: str = Field(..., min_length=1, max_length=1_000_000)
    title: str = Field("Supplier risk scan", max_length=200)
    prepared_for: str = Field("", max_length=200)


@app.post("/api/v1/scan")
async def scan_suppliers(body: ScanUpload, token: str = Depends(security)):
    """Scan a supplier list (CSV) against public records. Not stored; returns the report."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{INGESTION_URL}/scan", json=body.model_dump(), headers=_svc_headers(user),
                                         timeout=120.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            raise HTTPException(status_code=400, detail=e.response.json().get("detail"))
        raise HTTPException(status_code=502, detail="The scan failed")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Scanning is unavailable")


class SupplierImportBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=20_000_000)
    column_map: Dict[str, str] = Field(default_factory=dict)
    decisions: Dict[str, str] = Field(default_factory=dict)
    deactivate_missing: bool = False
    apply: bool = False


@app.post("/api/v1/suppliers/import/sap")
async def import_sap_suppliers(body: SupplierImportBody, token: str = Depends(security)):
    """Import the supplier master from an SAP LFA1 extract. Preview by default; apply=true writes."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/suppliers/import/sap", json=body.model_dump(),
                                         headers=_svc_headers(user), timeout=300.0)
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 422):
            detail = e.response.json().get("detail")
            raise HTTPException(status_code=400, detail=detail if isinstance(detail, str) else "The file could not be read")
        if e.response.status_code == 409:
            raise HTTPException(status_code=409, detail=e.response.json().get("detail"))
        raise HTTPException(status_code=502, detail="The import failed")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Supplier service unavailable")
    if body.apply:
        # Counts only: the file itself is customer data and stays out of the audit log.
        try:
            await audit_store.record_audit(user.organization_id, {
                "user_id": user.id, "actor_type": "user", "actor": user.email, "action": "suppliers.import.sap",
                "resource_type": "suppliers", "status_code": 200,
                "details": {"rows": result.get("rows"), "written": result.get("written"), "summary": result.get("summary"),
                            "missing_deactivated": result.get("missing_deactivated")}})
        except Exception as exc:
            logger.error("Audit write failed", error=type(exc).__name__, action="suppliers.import.sap")
    return result


class SpendImportBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000_000)
    column_map: Dict[str, str] = Field(default_factory=dict)
    decimal: Optional[str] = Field(None, pattern=r"^[.,]$")
    apply: bool = False


@app.post("/api/v1/suppliers/import/sap-spend")
async def import_sap_spend(body: SpendImportBody, token: str = Depends(security)):
    """12-month purchase-order spend per SAP supplier. Preview by default; apply=true writes."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/suppliers/import/sap-spend", json=body.model_dump(),
                                         headers=_svc_headers(user), timeout=300.0)
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 409, 422):
            detail = e.response.json().get("detail")
            raise HTTPException(status_code=400 if e.response.status_code == 422 else e.response.status_code,
                                detail=detail if isinstance(detail, str) else "The file could not be read")
        raise HTTPException(status_code=502, detail="The import failed")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Supplier service unavailable")
    if body.apply:
        # Totals only: order lines and amounts per supplier stay out of the audit log.
        try:
            await audit_store.record_audit(user.organization_id, {
                "user_id": user.id, "actor_type": "user", "actor": user.email, "action": "suppliers.import.sap_spend",
                "resource_type": "suppliers", "status_code": 200,
                "details": {"written": result.get("written"), "period": result.get("period"),
                            "lines": result.get("lines"), "unknown_suppliers": result.get("unknown_count")}})
        except Exception as exc:
            logger.error("Audit write failed", error=type(exc).__name__, action="suppliers.import.sap_spend")
    return result


# --- Direct SAP connection (S/4HANA OData; libs/integrations/sap_odata.py) ---

async def _sap_call(user, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: float = 30.0):
    """Call the coordinator for the SAP connection. Its messages for 400/404/409/502 are
    written for the person (SAP's status, never SAP's response body) and pass through."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(method, f"{COORDINATOR_URL}{path}", json=body,
                                             headers=_svc_headers(user), timeout=timeout)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code in (400, 404, 409, 422, 502):
            detail = e.response.json().get("detail")
            raise HTTPException(status_code=400 if code == 422 else code,
                                detail=detail if isinstance(detail, str) else "Invalid SAP connection settings")
        raise HTTPException(status_code=502, detail="The SAP request failed")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Supplier service unavailable")


async def _audit(user, action: str, details: Dict[str, Any]) -> None:
    try:
        await audit_store.record_audit(user.organization_id, {
            "user_id": user.id, "actor_type": "user", "actor": user.email, "action": action,
            "resource_type": "integrations", "status_code": 200, "details": details})
    except Exception as exc:
        logger.error("Audit write failed", error=type(exc).__name__, action=action)


class SapConnectionSettings(BaseModel):
    base_url: str = Field(..., min_length=8, max_length=500)
    sap_client: Optional[str] = Field(None, max_length=3)
    username: str = Field(..., min_length=1, max_length=200)
    password: Optional[str] = Field(None, min_length=1, max_length=500)


class SapConnectionSupplierImport(BaseModel):
    decisions: Dict[str, str] = Field(default_factory=dict)
    deactivate_missing: bool = False
    apply: bool = False


class SapConnectionSpendImport(BaseModel):
    apply: bool = False


@app.get("/api/v1/integrations/sap")
async def get_sap_connection(token: str = Depends(security)):
    """The organization's SAP connection (never its password)."""
    user = await verify_token(token.credentials)
    return await _sap_call(user, "GET", "/integrations/sap")


@app.put("/api/v1/integrations/sap")
async def save_sap_connection(body: SapConnectionSettings, token: str = Depends(security)):
    """Set up or change the SAP connection (admins). Leave out the password to keep it."""
    user = await verify_token(token.credentials)
    _require_admin(user, "set up the SAP connection")
    result = await _sap_call(user, "PUT", "/integrations/sap", {**body.model_dump(), "actor": user.email})
    # The address and user name are settings, not secrets; the password never reaches the log.
    await _audit(user, "integrations.sap.save", {"base_url": result["connection"]["base_url"],
                                                 "username": result["connection"]["username"],
                                                 "password_changed": body.password is not None})
    return result


@app.delete("/api/v1/integrations/sap")
async def delete_sap_connection(token: str = Depends(security)):
    """Remove the SAP connection and its stored password (admins)."""
    user = await verify_token(token.credentials)
    _require_admin(user, "remove the SAP connection")
    result = await _sap_call(user, "DELETE", "/integrations/sap")
    await _audit(user, "integrations.sap.delete", {})
    return result


@app.post("/api/v1/integrations/sap/test")
async def test_sap_connection(token: str = Depends(security)):
    """Check that SCIRM can read both SAP services with the stored settings (admins)."""
    user = await verify_token(token.credentials)
    _require_admin(user, "test the SAP connection")
    result = await _sap_call(user, "POST", "/integrations/sap/test", timeout=120.0)
    await _audit(user, "integrations.sap.test", {"ok": result.get("ok")})
    return result


@app.post("/api/v1/suppliers/import/sap/connection")
async def import_sap_suppliers_from_connection(body: SapConnectionSupplierImport, token: str = Depends(security)):
    """Import the supplier master from the organization's SAP system. Preview by default."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    result = await _sap_call(user, "POST", "/suppliers/import/sap/connection", body.model_dump(), timeout=300.0)
    if body.apply:
        await _audit(user, "suppliers.import.sap", {
            "source": "connection", "rows": result.get("rows"), "written": result.get("written"),
            "summary": result.get("summary"), "missing_deactivated": result.get("missing_deactivated")})
    return result


@app.post("/api/v1/suppliers/import/sap-spend/connection")
async def import_sap_spend_from_connection(body: SapConnectionSpendImport, token: str = Depends(security)):
    """Purchase-order spend for the last 365 days from the organization's SAP system."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    result = await _sap_call(user, "POST", "/suppliers/import/sap-spend/connection", body.model_dump(), timeout=300.0)
    if body.apply:
        await _audit(user, "suppliers.import.sap_spend", {
            "source": "connection", "written": result.get("written"), "period": result.get("period"),
            "lines": result.get("lines"), "unknown_suppliers": result.get("unknown_count")})
    return result


@app.get("/api/v1/signals/suppliers")
async def signals_overview(since_days: int = 365, token: str = Depends(security)):
    """Public incident and exposure counts for every supplier of the caller's organization."""
    user = await verify_token(token.credentials)
    return await _coordinator_get(user, "/signals/suppliers", {"since_days": since_days}, "Supplier signals unavailable")


# --- Feedback on matches and answers (Phase 1 gate metrics) ---

_REF = r"^[A-Za-z0-9._:\-]{1,200}$"

# Only these context fields are kept, so free text (such as the question asked) is never stored.
_FEEDBACK_CONTEXT = {
    "signal_match": {"match_type": str, "confidence": float, "source": str},
    "answer": {"citations": int, "method": str, "status": str},
    "citation": {"source": str, "signal_id": str, "match_kind": str},
}


class FeedbackRequest(BaseModel):
    target_type: str
    verdict: str
    # signal_match: the signal id (rated as a match to supplier_id). answer: an id the client
    # gives the answer it showed. citation: "<answer id>:<citation id>".
    target_id: str = Field(..., pattern=_REF)
    supplier_id: Optional[str] = Field(None, pattern=_REF)
    reason: Optional[str] = Field(None, max_length=500)
    context: Dict[str, Any] = Field(default_factory=dict)


def _feedback_context(target_type: str, context: Dict[str, Any]) -> Dict[str, Any]:
    kept = {}
    for key, kind in _FEEDBACK_CONTEXT[target_type].items():
        value = context.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            value = kind(value)
        except (TypeError, ValueError):
            continue
        kept[key] = value[:100] if isinstance(value, str) else value
    return kept


@app.post("/api/v1/feedback")
async def record_feedback(body: FeedbackRequest, token: str = Depends(security)):
    """Rate a matched record or an answer. One rating per person per item; rating again replaces it."""
    user = await verify_token(token.credentials)
    allowed = FEEDBACK_VERDICTS.get(body.target_type)
    if allowed is None:
        raise HTTPException(status_code=400, detail=f"target_type must be one of: {', '.join(FEEDBACK_VERDICTS)}")
    if body.verdict not in allowed:
        raise HTTPException(status_code=400, detail=f"verdict for {body.target_type} must be one of: {', '.join(allowed)}")
    if body.target_type == "signal_match" and not body.supplier_id:
        raise HTTPException(status_code=400, detail="supplier_id is required when rating a matched record")
    # A record can match several suppliers; the rating is about this pairing.
    target_id = f"{body.supplier_id}:{body.target_id}" if body.target_type == "signal_match" else body.target_id
    reason = (body.reason or "").strip() or None
    return await audit_store.record_feedback(user.organization_id, user.id, {
        "target_type": body.target_type, "target_id": target_id, "supplier_id": body.supplier_id,
        "verdict": body.verdict, "reason": reason, "context": _feedback_context(body.target_type, body.context)})


@app.get("/api/v1/suppliers/{supplier_id}/feedback")
async def my_supplier_feedback(supplier_id: str, token: str = Depends(security)):
    """The caller's own ratings of this supplier's matched records, keyed by signal id."""
    user = await verify_token(token.credentials)
    prefix = f"{supplier_id}:"
    rows = await audit_store.my_feedback_for_supplier(user.organization_id, user.id, supplier_id)
    return {"ratings": {k[len(prefix):]: v for k, v in rows.items() if k.startswith(prefix)}}


@app.get("/api/v1/feedback/summary")
async def feedback_summary(since_days: int = 90, token: str = Depends(security)):
    """Pilot metrics from ratings (admins and auditors only)."""
    user = await verify_token(token.credentials)
    if not {"admin", "auditor"} & set(user.roles):
        raise HTTPException(status_code=403, detail="Admins and auditors only")
    since_days = min(max(since_days, 1), 3650)
    summary = await audit_store.feedback_summary(user.organization_id, datetime.utcnow() - timedelta(days=since_days))
    return {"since_days": since_days, **summary}

# --- Alerts ---

@app.get("/api/v1/alerts")
async def list_alerts(
    status: str = None, severity: str = None, limit: int = 50,
    token: str = Depends(security),
):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {"limit": limit}
            if status:
                params["status_filter"] = status
            if severity:
                params["severity"] = severity
            response = await client.get(f"{COORDINATOR_URL}/alerts", params=params, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch alerts", error=str(e))
        raise HTTPException(status_code=500, detail="Alert service unavailable")

# --- Predictions ---

@app.get("/api/v1/predictions")
async def get_predictions(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/predictions", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch predictions", error=str(e))
        raise HTTPException(status_code=500, detail="Prediction service unavailable")

# --- Supply Chain Map ---

@app.get("/api/v1/supply-chain/map")
async def supply_chain_map(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {}
            response = await client.get(f"{COORDINATOR_URL}/supply-chain/map", params=params, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch supply chain map", error=str(e))
        raise HTTPException(status_code=500, detail="Supply chain map unavailable")

# --- Scenario Simulation ---

@app.post("/api/v1/scenarios/simulate")
async def simulate_scenario(scenario: Dict[str, Any], token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{COORDINATOR_URL}/scenarios/simulate",
                json=scenario, headers=_svc_headers(user), timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Scenario simulation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Scenario simulation failed")

# --- Chat ---

@app.post("/api/v1/chat")
async def chat(body: Dict[str, Any], token: str = Depends(security)):
    """Natural language query interface."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{CHAT_URL}/chat", json=body, headers=_svc_headers(user), timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Chat failed", error=str(e))
        raise HTTPException(status_code=500, detail="Chat service unavailable")

# --- Intelligence Feed ---

@app.post("/api/v1/intelligence/ingest")
async def trigger_ingestion(token: str = Depends(security)):
    """Trigger data ingestion from all sources."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{INGESTION_URL}/ingest", headers=_svc_headers(user), timeout=180.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Ingestion service unavailable")

@app.get("/api/v1/intelligence/feed")
async def intelligence_feed(source: str = None, limit: int = 50, token: str = Depends(security)):
    """Get intelligence feed documents."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {"limit": limit}
            if source:
                params["source"] = source
            response = await client.get(f"{INGESTION_URL}/documents", params=params, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Intelligence feed unavailable")

@app.get("/api/v1/intelligence/sources")
async def intelligence_sources(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{INGESTION_URL}/sources", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Source status unavailable")

# --- Data Export ---

@app.get("/api/v1/export/risks")
async def export_risks(format: str = "csv", token: str = Depends(security)):
    """Export all risks as CSV or JSON."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/risks", params={"limit": 1000}, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            data = response.json()
            risks = data.get("risks", [])

        if format == "csv":
            import io, csv
            output = io.StringIO()
            if risks:
                writer = csv.DictWriter(output, fieldnames=risks[0].keys())
                writer.writeheader()
                writer.writerows(risks)
            from fastapi.responses import StreamingResponse
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=scirm_risks_export.csv"},
            )
        return {"risks": risks, "total": len(risks), "exported_at": datetime.utcnow().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Export failed")

@app.get("/api/v1/export/suppliers")
async def export_suppliers(format: str = "csv", token: str = Depends(security)):
    """Export all suppliers as CSV or JSON."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/suppliers", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            data = response.json()
            suppliers = data.get("suppliers", [])

        if format == "csv":
            import io, csv
            output = io.StringIO()
            if suppliers:
                writer = csv.DictWriter(output, fieldnames=suppliers[0].keys())
                writer.writeheader()
                writer.writerows(suppliers)
            from fastapi.responses import StreamingResponse
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=scirm_suppliers_export.csv"},
            )
        return {"suppliers": suppliers, "total": len(suppliers), "exported_at": datetime.utcnow().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Export failed")

@app.get("/api/v1/export/report")
async def export_full_report(token: str = Depends(security)):
    """Export comprehensive risk report as JSON."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            risks_resp = await client.get(f"{COORDINATOR_URL}/risks", params={"limit": 500}, headers=_svc_headers(user), timeout=10.0)
            suppliers_resp = await client.get(f"{COORDINATOR_URL}/suppliers", headers=_svc_headers(user), timeout=10.0)
            alerts_resp = await client.get(f"{COORDINATOR_URL}/alerts", headers=_svc_headers(user), timeout=10.0)
            predictions_resp = await client.get(f"{COORDINATOR_URL}/predictions", headers=_svc_headers(user), timeout=10.0)

        return {
            "report_title": "SCIRM Supply Chain Risk Report",
            "generated_at": datetime.utcnow().isoformat(),
            "generated_by": user.email,
            "risks": risks_resp.json() if risks_resp.status_code == 200 else {},
            "suppliers": suppliers_resp.json() if suppliers_resp.status_code == 200 else {},
            "alerts": alerts_resp.json() if alerts_resp.status_code == 200 else {},
            "predictions": predictions_resp.json() if predictions_resp.status_code == 200 else {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Report generation failed")

# --- Password Reset ---

PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
_RESET_SENT = "If an account exists for this email, a reset link has been sent. It works once, for 30 minutes."


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


async def _send_reset_email(account: Dict[str, Any], token_value: str) -> None:
    link = f"{PUBLIC_APP_URL}/reset-password#{token_value}" if PUBLIC_APP_URL else f"/reset-password#{token_value}"
    text = (f"Hello {account.get('name') or ''},\n\nSomeone (hopefully you) asked to reset the SCIRM password for "
            f"{account['email']}. Open this link within {PASSWORD_RESET_MINUTES} minutes to choose a new one:\n\n"
            f"{link}\n\nIf you did not ask for this, ignore this email; your password stays the same.\n")
    html_body = (f"<p>Someone (hopefully you) asked to reset the SCIRM password for {account['email']}.</p>"
                 f"<p><a href=\"{link}\">Choose a new password</a> (works once, for {PASSWORD_RESET_MINUTES} minutes).</p>"
                 "<p>If you did not ask for this, ignore this email; your password stays the same.</p>")
    try:
        await reports.send_email([account["email"]], "Reset your SCIRM password", text, html_body)
    except Exception as exc:
        logger.error("Password reset email failed", error=type(exc).__name__)


@app.post("/api/v1/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    """Email a single-use reset link. The answer is the same whether or not the account
    exists, and the email is sent in the background so timing does not tell either."""
    if reports.smtp_config() is None:
        raise HTTPException(status_code=503, detail="Password reset by email is not set up on this deployment. "
                                                    "Ask an administrator of your organization.")
    import hashlib
    token_value = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_MINUTES)).isoformat()
    account = await audit_store.request_password_reset(body.email.strip().lower(),
                                                       hashlib.sha256(token_value.encode()).hexdigest(), expires)
    if account:
        await _audit_event(str(account["organization_id"]), str(account["user_id"]), account["email"],
                           "auth.password_reset_requested")
        asyncio.create_task(_send_reset_email(account, token_value))
    return {"message": _RESET_SENT}


@app.post("/api/v1/auth/reset-password")
async def reset_password(body: ResetPasswordRequest):
    """Set a new password with a reset link's token. Other sessions are signed out."""
    import hashlib
    _password_ok(body.new_password)
    done = await audit_store.consume_password_reset(hashlib.sha256(body.token.encode()).hexdigest(),
                                                    get_password_hash(body.new_password))
    if not done:
        raise HTTPException(status_code=400, detail="This reset link is not valid any more. Ask for a new one.")
    await _audit_event(str(done["organization_id"]), str(done["user_id"]), done["email"], "auth.password_reset")
    return {"message": "Your password has been reset. Sign in with the new one."}


@app.post("/api/v1/auth/change-password")
async def change_password(body: ChangePasswordRequest, token: str = Depends(security)):
    """Change the caller's password. Other sessions are signed out; this one gets new tokens."""
    user = await verify_token(token.credentials)
    if DEV_USERS.get(user.email.lower()):
        raise HTTPException(status_code=400, detail="Demo accounts use DEV_PASSWORD and cannot change it.")
    _password_ok(body.new_password)
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="Choose a password different from the current one.")
    if not await _check_password(user.email, body.current_password):
        raise HTTPException(status_code=400, detail="The current password is not correct.")
    if not await audit_store.set_password(user.organization_id, user.id, get_password_hash(body.new_password)):
        raise HTTPException(status_code=404, detail="Account not found")
    found = await _find_user_by_id(user.id)
    return {"message": "Password changed. Other sessions are signed out.", **_issue_tokens(*found)}

# --- Components ---

@app.get("/api/v1/components")
async def list_components(category: str = None, criticality: str = None, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {}
            if category: params["category"] = category
            if criticality: params["criticality"] = criticality
            response = await client.get(f"{COMPONENT_TRACKER_URL}/components", params=params, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Component tracker unavailable")

@app.get("/api/v1/products")
async def list_products(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COMPONENT_TRACKER_URL}/products", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Component tracker unavailable")

@app.get("/api/v1/products/{product_id}/bom")
async def get_product_bom(product_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COMPONENT_TRACKER_URL}/products/{quote(product_id, safe='')}/bom", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Component tracker unavailable")

@app.get("/api/v1/components/{component_id}/impact")
async def component_impact(component_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COMPONENT_TRACKER_URL}/impact-analysis/{quote(component_id, safe='')}", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Component tracker unavailable")

# --- Digital Twin Simulator ---

@app.post("/api/v1/simulator/run")
async def run_simulation(body: Dict[str, Any], token: str = Depends(security)):
    """Run Monte Carlo simulation."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{SIMULATOR_URL}/simulate", json=body, headers=_svc_headers(user), timeout=60.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Simulation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Simulator unavailable")

# --- Procurement ---

@app.post("/api/v1/procurement/evaluate")
async def evaluate_procurement(body: Dict[str, Any], token: str = Depends(security)):
    """Evaluate suppliers and generate procurement actions."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{PROCUREMENT_URL}/evaluate", json=body, headers=_svc_headers(user), timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Procurement service unavailable")

@app.get("/api/v1/procurement/actions")
async def procurement_actions(status: str = None, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {}
            if status:
                params["status"] = status
            response = await client.get(f"{PROCUREMENT_URL}/actions", params=params, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Procurement service unavailable")

@app.get("/api/v1/procurement/alternatives/{supplier_name}")
async def procurement_alternatives(supplier_name: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{PROCUREMENT_URL}/alternatives/{quote(supplier_name, safe='')}", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Procurement service unavailable")

# --- Risk CRUD ---

@app.post("/api/v1/risks")
async def create_risk(body: Dict[str, Any], token: str = Depends(security)):
    """Create a manual risk entry."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/risks", json=body, headers=_svc_headers(user), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Risk creation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Risk service unavailable")

@app.put("/api/v1/risks/{risk_id}")
async def update_risk(risk_id: str, body: Dict[str, Any], token: str = Depends(security)):
    """Update a risk entry."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{COORDINATOR_URL}/risks/{quote(risk_id, safe='')}", json=body, headers=_svc_headers(user), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Risk update failed", error=str(e))
        raise HTTPException(status_code=500, detail="Risk service unavailable")

# --- Supplier CRUD ---

@app.post("/api/v1/suppliers")
async def create_supplier(body: Dict[str, Any], token: str = Depends(security)):
    """Create a new supplier."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/suppliers", json=body, headers=_svc_headers(user), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Supplier creation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Supplier service unavailable")

@app.put("/api/v1/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, body: Dict[str, Any], token: str = Depends(security)):
    """Update an existing supplier."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{COORDINATOR_URL}/suppliers/{quote(supplier_id, safe='')}", json=body, headers=_svc_headers(user), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Supplier update failed", error=str(e))
        raise HTTPException(status_code=500, detail="Supplier service unavailable")

# --- Alert Actions ---

@app.post("/api/v1/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, token: str = Depends(security)):
    """Acknowledge an active alert."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/alerts/{quote(alert_id, safe='')}/acknowledge", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Alert acknowledge failed", error=str(e))
        raise HTTPException(status_code=500, detail="Alert service unavailable")

# --- Sub-Tier Discovery ---

@app.post("/api/v1/suppliers/discover-subtiers")
async def discover_subtiers(body: Dict[str, Any], token: str = Depends(security)):
    """Discover sub-tier suppliers using AI."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/discover-subtiers", json=body, headers=_svc_headers(user), timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Discovery failed", error=str(e))
        raise HTTPException(status_code=500, detail="Discovery service unavailable")

# --- Risk Events ---

@app.post("/api/v1/events")
async def create_risk_event(body: Dict[str, Any], token: str = Depends(security)):
    """Create a risk event with impact propagation."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/events", json=body, headers=_svc_headers(user), timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Event creation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Event service unavailable")

@app.get("/api/v1/events")
async def list_events(limit: int = 50, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/events", params={"limit": limit}, headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Event service unavailable")

@app.get("/api/v1/events/{event_id}/impacts")
async def get_event_impacts(event_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/events/{quote(event_id, safe='')}/impacts", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Impact data unavailable")

# --- Risk Scoring ---

@app.post("/api/v1/risk-score")
async def score_supplier_risk(body: Dict[str, Any], token: str = Depends(security)):
    """Score a supplier across 7 risk dimensions."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{RISK_SCORER_URL}/score", json=body, headers=_svc_headers(user), timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Risk scoring failed", error=str(e))
        raise HTTPException(status_code=500, detail="Risk scoring service unavailable")

@app.get("/api/v1/risk-dimensions")
async def list_risk_dimensions(token: str = Depends(security)):
    """List all 7 risk dimensions with rubrics."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{RISK_SCORER_URL}/dimensions", headers=_svc_headers(user), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Risk scoring service unavailable")

# --- ERP Integration ---

AUDIT_EXPORT_MAX = 50_000
_AUDIT_CSV_COLUMNS = ("created_at", "actor", "actor_type", "action", "category", "resource_type", "resource_id",
                      "status_code", "ip_address", "details", "id")


async def _audit_reader(token: str):
    user = await verify_token(token)
    if not {"admin", "auditor"} & set(user.roles):
        raise HTTPException(status_code=403, detail="Admins and auditors only")
    return user


def _audit_filters(category: Optional[str], actor: Optional[str], failed: bool, since: Optional[str],
                   until: Optional[str], before: Optional[str] = None) -> Dict[str, Any]:
    if category and category not in AUDIT_CATEGORY_NAMES:
        raise HTTPException(status_code=400, detail=f"category must be one of: {', '.join(AUDIT_CATEGORY_NAMES)}")
    for name, value in (("since", since), ("until", until)):
        if value:
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"{name} must be an ISO date or time")
    if before and "|" not in before:
        raise HTTPException(status_code=400, detail="Invalid cursor")
    return {"category": category, "actor": (actor or "").strip()[:255] or None, "failed": failed,
            "since": since, "until": until, "before": before}


def _audit_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    details = entry.get("details")
    if isinstance(details, str):  # asyncpg returns json as text
        try:
            details = json.loads(details)
        except ValueError:
            details = {"raw": details}
    return {**entry, "details": details or {}, "category": audit_category(entry.get("action") or "")}


@app.get("/api/v1/audit")
async def list_audit_log(limit: int = 100, category: Optional[str] = None, actor: Optional[str] = None,
                         failed: bool = False, since: Optional[str] = None, until: Optional[str] = None,
                         before: Optional[str] = None, token: str = Depends(security)):
    """Audit trail for the caller's organization, newest first (admins and auditors only).
    Filter by category (sign_in, access, integrations, changes), actor (part of the email),
    failed (status 400 or more) and a time range; page with next_cursor -> before."""
    user = await _audit_reader(token.credentials)
    limit = min(max(limit, 1), 500)
    filters = _audit_filters(category, actor, failed, since, until, before)
    # One extra row tells whether there is another page, without a count over the table.
    rows = await audit_store.list_audit(user.organization_id, limit=limit + 1, filters=filters)
    entries = [_audit_view(e) for e in rows[:limit]]
    return {"entries": entries, "total": len(entries),
            "next_cursor": audit_cursor(rows[limit - 1]) if len(rows) > limit else None}


@app.get("/api/v1/audit/export")
async def export_audit_log(category: Optional[str] = None, actor: Optional[str] = None, failed: bool = False,
                           since: Optional[str] = None, until: Optional[str] = None, token: str = Depends(security)):
    """The filtered audit trail as CSV, newest first, up to AUDIT_EXPORT_MAX rows. The
    export itself is recorded in the audit log."""
    import csv
    import io
    from fastapi.responses import Response
    user = await _audit_reader(token.credentials)
    filters = _audit_filters(category, actor, failed, since, until)
    rows: List[Dict[str, Any]] = []
    while len(rows) < AUDIT_EXPORT_MAX:
        page = await audit_store.list_audit(user.organization_id, limit=min(1000, AUDIT_EXPORT_MAX - len(rows)),
                                            filters=filters)
        rows.extend(page)
        if len(page) < 1000:
            break
        filters = {**filters, "before": audit_cursor(page[-1])}
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["created_at_utc", *_AUDIT_CSV_COLUMNS[1:]])  # stored as UTC without a zone
    for entry in map(_audit_view, rows):
        values = {**entry, "details": json.dumps(entry["details"], default=str, sort_keys=True)}
        # Cells that a spreadsheet would run as a formula are prefixed (CSV injection).
        writer.writerow(["'" + str(v) if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else
                         ("" if v is None else v) for v in (values.get(c) for c in _AUDIT_CSV_COLUMNS)])
    await _audit_event(user.organization_id, user.id, user.email, "audit.exported")
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="scirm-audit-{stamp}.csv"',
        "X-Rows": str(len(rows)), "X-Truncated": "true" if len(rows) >= AUDIT_EXPORT_MAX else "false"})


# WebSocket for real-time updates
class ConnectionManager:
    """Tracks authenticated WebSocket clients per organization."""

    def __init__(self):
        self.connections: Dict[str, list] = {}

    def add(self, org_id: str, websocket: WebSocket):
        self.connections.setdefault(org_id, []).append(websocket)

    def disconnect(self, org_id: str, websocket: WebSocket):
        clients = self.connections.get(org_id, [])
        if websocket in clients:
            clients.remove(websocket)

    async def broadcast(self, org_id: str, message: dict):
        """Send a message to one organization's clients only."""
        for connection in list(self.connections.get(org_id, [])):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(org_id, connection)

manager = ConnectionManager()

WS_AUTH_TIMEOUT_SECONDS = 10


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time risk updates.

    The client must send {"token": "<access token>"} as its first message.
    The token is not accepted in the URL, where it would end up in access logs.
    """
    allowed_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
    origin = websocket.headers.get("origin")
    if origin and origin not in allowed_origins:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=WS_AUTH_TIMEOUT_SECONDS)
        user = await verify_token(str(first.get("token", "")))
    except (asyncio.TimeoutError, HTTPException, ValueError, AttributeError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return

    manager.add(user.organization_id, websocket)
    try:
        await websocket.send_json({"event": "authenticated"})
        while True:
            # Keep the connection alive; client messages are ignored for now.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.organization_id, websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_GATEWAY_PORT", 8000)),
        reload=os.getenv("RELOAD", "false").lower() == "true"
    )
