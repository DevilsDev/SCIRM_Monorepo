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
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if request.password != DEV_PASSWORD:
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
