"""
SCIRM API Gateway
Central entry point for all client requests, routing to appropriate agent services.
"""

import os
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from uuid import uuid4

import jwt
import httpx
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from pydantic import BaseModel
import structlog

from libs.common.auth import (
    verify_token, create_access_token, create_refresh_token, verify_password,
    get_password_hash, generate_totp_secret, get_totp_uri, verify_totp,
    MFA_ENABLED, SECRET_KEY, ALGORITHM,
)
from libs.common.monitoring import setup_monitoring
from libs.common.models import RiskAssessmentRequest, RiskAssessmentResponse
from libs.common.security import setup_cors, setup_rate_limiting
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SCIRM API Gateway")
    yield
    logger.info("Shutting down SCIRM API Gateway")

app = FastAPI(
    title="SCIRM API Gateway",
    description="AI-Powered Supply Chain Risk Management Platform",
    version="1.0.0",
    lifespan=lifespan,
)

setup_cors(app)
setup_rate_limiting(app, requests_per_minute=100, burst=200)
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
    organization_id: Optional[str] = None

# In-memory user store for development (production would use database)
_registered_users: Dict[str, Dict[str, Any]] = {}

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

DEV_PASSWORD = "scirm-dev-2026"
DEV_USERS = {
    "sarah.chen@pharmacorp.com": {"id": "b0000000-0000-0000-0000-000000000001", "name": "Sarah Chen", "roles": ["admin", "analyst"], "org_id": "a0000000-0000-0000-0000-000000000001", "mfa_secret": None},
    "marcus.rodriguez@pharmacorp.com": {"id": "b0000000-0000-0000-0000-000000000002", "name": "Marcus Rodriguez", "roles": ["analyst"], "org_id": "a0000000-0000-0000-0000-000000000001", "mfa_secret": None},
    "lisa.park@medtech.com": {"id": "b0000000-0000-0000-0000-000000000003", "name": "Lisa Park", "roles": ["admin", "analyst"], "org_id": "a0000000-0000-0000-0000-000000000002", "mfa_secret": None},
    "auditor@scirm.dev": {"id": "b0000000-0000-0000-0000-000000000004", "name": "SCIRM Auditor", "roles": ["auditor", "viewer"], "org_id": "default-org", "mfa_secret": None},
}


class MFAVerifyRequest(BaseModel):
    email: str
    totp_code: str
    mfa_token: str


@app.post("/api/v1/auth/login")
async def login(request: LoginRequest):
    """Authenticate user. If MFA is enabled, returns mfa_required=true with a temporary token."""
    user_info = DEV_USERS.get(request.email)
    registered = _registered_users.get(request.email)

    if not user_info and not registered:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check password: registered users use their own password, dev users use DEV_PASSWORD
    if registered:
        if request.password != registered.get("password"):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user_info:
            user_info = registered
    elif request.password != DEV_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if MFA is required
    if MFA_ENABLED and user_info.get("mfa_secret"):
        mfa_token = create_access_token(
            data={"sub": user_info["id"], "type": "mfa_pending", "email": request.email},
            expires_delta=timedelta(minutes=5),
        )
        return {"mfa_required": True, "mfa_token": mfa_token, "token_type": "bearer"}

    token = create_access_token(data={
        "sub": user_info["id"],
        "email": request.email,
        "name": user_info["name"],
        "roles": user_info["roles"],
        "org_id": user_info["org_id"],
    })
    refresh = create_refresh_token(user_info["id"])

    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer"}


@app.post("/api/v1/auth/mfa/verify")
async def verify_mfa(request: MFAVerifyRequest):
    """Verify TOTP code after initial login when MFA is enabled."""
    user_info = DEV_USERS.get(request.email)
    if not user_info or not user_info.get("mfa_secret"):
        raise HTTPException(status_code=400, detail="MFA not configured for this user")

    if not verify_totp(user_info["mfa_secret"], request.totp_code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")

    token = create_access_token(data={
        "sub": user_info["id"],
        "email": request.email,
        "name": user_info["name"],
        "roles": user_info["roles"],
        "org_id": user_info["org_id"],
    })
    refresh = create_refresh_token(user_info["id"])

    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer"}


@app.post("/api/v1/auth/mfa/setup")
async def setup_mfa(token: str = Depends(security)):
    """Generate a TOTP secret and QR code URI for MFA enrollment."""
    user = await verify_token(token.credentials)
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.email)

    # Store secret (in production, persist to DB)
    if user.email in DEV_USERS:
        DEV_USERS[user.email]["mfa_secret"] = secret

    return {"secret": secret, "otpauth_uri": uri, "message": "Scan the QR code with your authenticator app"}


@app.post("/api/v1/auth/refresh")
async def refresh_token(body: Dict[str, Any]):
    """Exchange a refresh token for a new access token."""
    refresh = body.get("refresh_token", "")
    if not refresh:
        raise HTTPException(status_code=400, detail="refresh_token required")

    try:
        payload = jwt.decode(refresh, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Find user by ID
    user_info = next((u for u in DEV_USERS.values() if u["id"] == user_id), None)
    email = next((e for e, u in DEV_USERS.items() if u["id"] == user_id), "")
    if not user_info:
        raise HTTPException(status_code=401, detail="User not found")

    new_token = create_access_token(data={
        "sub": user_info["id"],
        "email": email,
        "name": user_info["name"],
        "roles": user_info["roles"],
        "org_id": user_info["org_id"],
    })

    return {"access_token": new_token, "token_type": "bearer"}


@app.get("/api/v1/auth/oauth/authorize")
async def oauth_authorize(provider: str = "google", redirect_uri: str = "http://localhost:3000/auth/callback"):
    """
    OAuth 2.0 authorization endpoint — returns the provider's auth URL.
    In production, this redirects to the actual OAuth provider.
    """
    # Mock OAuth flow for development
    return {
        "provider": provider,
        "authorization_url": f"https://{provider}.com/oauth/authorize?client_id=scirm&redirect_uri={redirect_uri}&scope=openid+email+profile",
        "state": "mock-state-token",
        "message": "OAuth provider integration — redirect user to authorization_url",
    }


@app.post("/api/v1/auth/signup")
async def signup(request: SignupRequest):
    """Register a new user account."""
    # Check if email already taken (dev users + registered users)
    if request.email in DEV_USERS or request.email in _registered_users:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Validate password strength
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Create user
    user_id = str(uuid4())
    _registered_users[request.email] = {
        "id": user_id,
        "name": request.name,
        "roles": ["analyst"],  # Default role for new signups
        "org_id": request.organization_id or "default-org",
        "password": request.password,
        "mfa_secret": None,
        "created_at": datetime.utcnow().isoformat(),
    }

    # Also add to DEV_USERS so login works immediately
    DEV_USERS[request.email] = {
        "id": user_id,
        "name": request.name,
        "roles": ["analyst"],
        "org_id": request.organization_id or "default-org",
        "mfa_secret": None,
    }

    # Generate tokens
    token = create_access_token(data={
        "sub": user_id,
        "email": request.email,
        "name": request.name,
        "roles": ["analyst"],
        "org_id": request.organization_id or "default-org",
    })
    refresh = create_refresh_token(user_id)

    logger.info("User registered", email=request.email, user_id=user_id)

    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": request.email,
            "name": request.name,
            "roles": ["analyst"],
        },
    }


@app.post("/api/v1/risk-assessment", response_model=RiskAssessmentResponse)
async def assess_risk(
    request: RiskAssessmentRequest,
    token: str = Depends(security)
):
    """Initiate risk assessment through coordinator agent."""
    user = await verify_token(token.credentials)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{COORDINATOR_URL}/assess-risk",
                json=request.model_dump(mode="json"),
                headers={"Authorization": f"Bearer {token.credentials}"},
                timeout=30.0
            )
            response.raise_for_status()
            result = RiskAssessmentResponse(**response.json())

            # Broadcast real-time events to WebSocket clients
            await manager.broadcast({
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
                    await manager.broadcast({
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
                headers={"Authorization": f"Bearer {token.credentials}"},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    except httpx.HTTPError as e:
        logger.error("Failed to fetch risks", error=str(e))
        raise HTTPException(status_code=500, detail="Risk service unavailable")

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
                f"{COORDINATOR_URL}/risks/{risk_id}",
                headers={"Authorization": f"Bearer {token.credentials}"},
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
                f"{COORDINATOR_URL}/recommendations/{risk_id}",
                headers={"Authorization": f"Bearer {token.credentials}"},
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
    org_id: str = None, risk_tier: str = None, limit: int = 50,
    token: str = Depends(security),
):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {"limit": limit}
            if org_id:
                params["org_id"] = org_id
            if risk_tier:
                params["risk_tier"] = risk_tier
            response = await client.get(f"{COORDINATOR_URL}/suppliers", params=params, timeout=10.0)
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
            response = await client.get(f"{COORDINATOR_URL}/suppliers/{supplier_id}", timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=404, detail="Supplier not found")

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
            response = await client.get(f"{COORDINATOR_URL}/alerts", params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch alerts", error=str(e))
        raise HTTPException(status_code=500, detail="Alert service unavailable")

# --- Risk History ---

@app.get("/api/v1/risks/history")
async def risk_history(limit: int = 100, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/risks/history", params={"limit": limit}, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch risk history", error=str(e))
        raise HTTPException(status_code=500, detail="Risk history unavailable")

# --- Predictions ---

@app.get("/api/v1/predictions")
async def get_predictions(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/predictions", timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch predictions", error=str(e))
        raise HTTPException(status_code=500, detail="Prediction service unavailable")

# --- Supply Chain Map ---

@app.get("/api/v1/supply-chain/map")
async def supply_chain_map(org_id: str = None, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            params = {}
            if org_id:
                params["org_id"] = org_id
            response = await client.get(f"{COORDINATOR_URL}/supply-chain/map", params=params, timeout=10.0)
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
                json=scenario, timeout=30.0,
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
            response = await client.post(f"{CHAT_URL}/chat", json=body, timeout=30.0)
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
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{INGESTION_URL}/ingest", timeout=30.0)
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
            response = await client.get(f"{INGESTION_URL}/documents", params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Intelligence feed unavailable")

@app.get("/api/v1/intelligence/sources")
async def intelligence_sources(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{INGESTION_URL}/sources", timeout=10.0)
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
            response = await client.get(f"{COORDINATOR_URL}/risks", params={"limit": 1000}, timeout=10.0)
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
            response = await client.get(f"{COORDINATOR_URL}/suppliers", timeout=10.0)
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
            risks_resp = await client.get(f"{COORDINATOR_URL}/risks", params={"limit": 500}, timeout=10.0)
            suppliers_resp = await client.get(f"{COORDINATOR_URL}/suppliers", timeout=10.0)
            alerts_resp = await client.get(f"{COORDINATOR_URL}/alerts", timeout=10.0)
            predictions_resp = await client.get(f"{COORDINATOR_URL}/predictions", timeout=10.0)

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
            response = await client.get(f"{COMPONENT_TRACKER_URL}/components", params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Component tracker unavailable")

@app.get("/api/v1/products")
async def list_products(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COMPONENT_TRACKER_URL}/products", timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Component tracker unavailable")

@app.get("/api/v1/products/{product_id}/bom")
async def get_product_bom(product_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COMPONENT_TRACKER_URL}/products/{product_id}/bom", timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Component tracker unavailable")

@app.get("/api/v1/components/{component_id}/impact")
async def component_impact(component_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COMPONENT_TRACKER_URL}/impact-analysis/{component_id}", timeout=10.0)
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
            response = await client.post(f"{SIMULATOR_URL}/simulate", json=body, timeout=60.0)
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
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{PROCUREMENT_URL}/evaluate", json=body, timeout=30.0)
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
            response = await client.get(f"{PROCUREMENT_URL}/actions", params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Procurement service unavailable")

@app.get("/api/v1/procurement/alternatives/{supplier_name}")
async def procurement_alternatives(supplier_name: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{PROCUREMENT_URL}/alternatives/{supplier_name}", timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Procurement service unavailable")

# --- Risk CRUD ---

@app.post("/api/v1/risks")
async def create_risk(body: Dict[str, Any], token: str = Depends(security)):
    """Create a manual risk entry."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/risks", json=body, timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Risk creation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Risk service unavailable")

@app.put("/api/v1/risks/{risk_id}")
async def update_risk(risk_id: str, body: Dict[str, Any], token: str = Depends(security)):
    """Update a risk entry."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{COORDINATOR_URL}/risks/{risk_id}", json=body, timeout=15.0)
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
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/suppliers", json=body, timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error("Supplier creation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Supplier service unavailable")

@app.put("/api/v1/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, body: Dict[str, Any], token: str = Depends(security)):
    """Update an existing supplier."""
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{COORDINATOR_URL}/suppliers/{supplier_id}", json=body, timeout=15.0)
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
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/alerts/{alert_id}/acknowledge", timeout=10.0)
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
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/discover-subtiers", json=body, timeout=30.0)
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
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{COORDINATOR_URL}/events", json=body, timeout=30.0)
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
            response = await client.get(f"{COORDINATOR_URL}/events", params={"limit": limit}, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Event service unavailable")

@app.get("/api/v1/events/{event_id}/impacts")
async def get_event_impacts(event_id: str, token: str = Depends(security)):
    user = await verify_token(token.credentials)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COORDINATOR_URL}/events/{event_id}/impacts", timeout=10.0)
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
            response = await client.post(f"{RISK_SCORER_URL}/score", json=body, timeout=30.0)
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
            response = await client.get(f"{RISK_SCORER_URL}/dimensions", timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail="Risk scoring service unavailable")

# --- ERP Integration ---

@app.get("/api/v1/erp/status")
async def erp_status(token: str = Depends(security)):
    """Check connection status of all ERP adapters."""
    user = await verify_token(token.credentials)
    return erp_manager.health_check()

@app.post("/api/v1/erp/sync")
async def erp_sync(body: Dict[str, Any], token: str = Depends(security)):
    """Sync data from all connected ERP systems."""
    user = await verify_token(token.credentials)
    org_id = body.get("organization_id", "a0000000-0000-0000-0000-000000000001")
    await erp_manager.connect_all()
    results = await erp_manager.sync_all(org_id)
    return {"status": "completed", "results": results}

@app.get("/api/v1/erp/suppliers")
async def erp_suppliers(org_id: str = "a0000000-0000-0000-0000-000000000001", token: str = Depends(security)):
    """Fetch suppliers from all connected ERP systems."""
    user = await verify_token(token.credentials)
    await erp_manager.connect_all()
    suppliers = await erp_manager.sync_suppliers(org_id)
    return {"suppliers": suppliers, "total": len(suppliers)}

# WebSocket for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Remove disconnected clients
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time risk updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            # Echo back for now - in production, this would handle subscriptions
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_GATEWAY_PORT", 8000)),
        reload=os.getenv("RELOAD", "false").lower() == "true"
    )
