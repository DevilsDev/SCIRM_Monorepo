"""
SCIRM API Gateway
Central entry point for all client requests, routing to appropriate agent services.
"""

import asyncio
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from urllib.parse import quote, urlencode
from uuid import uuid4

import httpx
from datetime import datetime, timedelta
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
from libs.common.store import ROLES, EmailExists, LastAdmin, create_store
from libs.common.tenancy import internal_headers
from libs.integrations.manager import erp_manager

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


async def _audit_auth(action: str, email: str, user_info: Optional[Dict[str, Any]], ok: bool) -> None:
    try:
        await audit_store.record_audit(user_info["org_id"] if user_info else None, {
            "user_id": user_info["id"] if user_info else None,
            "actor_type": "user",
            "actor": email,
            "action": action if ok else f"{action}_failed",
            "resource_type": "auth",
            "status_code": 200 if ok else 401,
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
# Base for invitation links. Configured, never taken from the request's Host header.
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:3000" if IS_DEV else "").rstrip("/")
# Checked for unknown emails too, so response time does not reveal which accounts exist.
_DUMMY_PASSWORD_HASH = get_password_hash(secrets.token_urlsafe(16))


def _account_info(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": str(row["id"]), "name": row["name"], "roles": list(row["roles"] or []),
            "org_id": str(row["organization_id"]), "mfa_secret": row.get("mfa_secret"), "stored": True}


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


@app.post("/api/v1/auth/login")
async def login(request: LoginRequest):
    """Authenticate user. If MFA is enabled, returns mfa_required=true with a temporary token."""
    user_info = await _check_password(request.email, request.password)
    # Record the attempt with the email (never the password); the middleware cannot read bodies.
    await _audit_auth("auth.login", request.email, user_info, ok=bool(user_info))
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if MFA is required
    if MFA_ENABLED and user_info.get("mfa_secret"):
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
    if not user_info.get("mfa_secret"):
        raise HTTPException(status_code=400, detail="MFA not configured for this user")

    if not verify_totp(user_info["mfa_secret"], request.totp_code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")

    await _record_login(user_info)
    return _issue_tokens(email, user_info)


@app.post("/api/v1/auth/mfa/setup")
async def setup_mfa(token: str = Depends(security)):
    """Generate a TOTP secret and QR code URI for MFA enrollment."""
    user = await verify_token(token.credentials)
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.email)

    # Demo accounts keep it in memory; real accounts in the database. Note: stored in plain
    # text for now; encrypting TOTP secrets at rest is a follow-up.
    demo = DEV_USERS.get(user.email.lower())
    if demo:
        demo["mfa_secret"] = secret
    elif not await audit_store.set_mfa_secret(user.organization_id, user.id, secret):
        raise HTTPException(status_code=404, detail="Account not found")

    return {"secret": secret, "otpauth_uri": uri, "message": "Scan the QR code with your authenticator app"}


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


def _require_admin(user) -> None:
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Only administrators can manage the team")


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
    return {"members": await audit_store.list_members(user.organization_id)}


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
                 "org_id": str(accepted["organization_id"])}
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


@app.get("/api/v1/signals/suppliers")
async def signals_overview(since_days: int = 365, token: str = Depends(security)):
    """Public incident and exposure counts for every supplier of the caller's organization."""
    user = await verify_token(token.credentials)
    return await _coordinator_get(user, "/signals/suppliers", {"since_days": since_days}, "Supplier signals unavailable")

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

@app.post("/api/v1/auth/forgot-password")
async def forgot_password(body: Dict[str, Any]):
    """Request a password reset email."""
    email = body.get("email", "")
    # In production: generate token, send email via SMTP
    # For dev: just acknowledge
    logger.info("Password reset requested", email=email)
    return {"message": "If an account exists for this email, a reset link has been sent."}

@app.post("/api/v1/auth/reset-password")
async def reset_password(body: Dict[str, Any]):
    """Reset password with a token."""
    token_val = body.get("token", "")
    new_password = body.get("new_password", "")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    # In production: validate token, update password in DB
    return {"message": "Password has been reset successfully."}

@app.post("/api/v1/auth/change-password")
async def change_password(body: Dict[str, Any], token: str = Depends(security)):
    """Change password for authenticated user."""
    user = await verify_token(token.credentials)
    current = body.get("current_password", "")
    new_pass = body.get("new_password", "")
    if len(new_pass) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    # In production: verify current password, update in DB
    return {"message": "Password changed successfully."}

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

@app.get("/api/v1/audit")
async def list_audit_log(limit: int = 100, token: str = Depends(security)):
    """Audit trail for the caller's organization (admins and auditors only)."""
    user = await verify_token(token.credentials)
    if not {"admin", "auditor"} & set(user.roles):
        raise HTTPException(status_code=403, detail="Admins and auditors only")
    entries = await audit_store.list_audit(user.organization_id, limit=min(max(limit, 1), 1000))
    return {"entries": entries, "total": len(entries)}


@app.get("/api/v1/erp/status")
async def erp_status(token: str = Depends(security)):
    """Check connection status of all ERP adapters."""
    user = await verify_token(token.credentials)
    return erp_manager.health_check()

@app.post("/api/v1/erp/sync")
async def erp_sync(body: Dict[str, Any], token: str = Depends(security)):
    """Sync data from all connected ERP systems."""
    user = await verify_token(token.credentials)
    require_write_access(user)
    await erp_manager.connect_all()
    results = await erp_manager.sync_all(user.organization_id)
    return {"status": "completed", "results": results}

@app.get("/api/v1/erp/suppliers")
async def erp_suppliers(token: str = Depends(security)):
    """Fetch suppliers from all connected ERP systems."""
    user = await verify_token(token.credentials)
    await erp_manager.connect_all()
    suppliers = await erp_manager.sync_suppliers(user.organization_id)
    return {"suppliers": suppliers, "total": len(suppliers)}

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
