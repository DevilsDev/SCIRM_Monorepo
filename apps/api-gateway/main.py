"""
SCIRM API Gateway
Central entry point for all client requests, routing to appropriate agent services.
"""

import os
from contextlib import asynccontextmanager
from typing import Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from pydantic import BaseModel
import structlog

from libs.common.auth import verify_token, create_access_token, verify_password
from libs.common.monitoring import setup_monitoring
from libs.common.models import RiskAssessmentRequest, RiskAssessmentResponse
from libs.common.security import setup_cors, setup_rate_limiting

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
    """Application lifespan management."""
    logger.info("Starting SCIRM API Gateway")
    setup_monitoring(app)
    yield
    logger.info("Shutting down SCIRM API Gateway")

app = FastAPI(
    title="SCIRM API Gateway",
    description="AI-Powered Supply Chain Risk Management Platform",
    version="1.0.0",
    lifespan=lifespan
)

setup_cors(app)
setup_rate_limiting(app, requests_per_minute=100, burst=200)

class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]

class LoginRequest(BaseModel):
    email: str
    password: str

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

@app.post("/api/v1/auth/login")
async def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    # Dev users with hashed passwords (bcrypt hash of "scirm-dev-2026")
    DEV_PASSWORD_HASH = "$2b$12$LJ3m5ZQxPxE5tQxKqG5pXOqEwQG1jNqIvHO.QJ5fNqXL5Z4J5X5bK"
    dev_users = {
        "sarah.chen@pharmacorp.com": {"id": "b0000000-0000-0000-0000-000000000001", "name": "Sarah Chen", "roles": ["admin", "analyst"], "org_id": "a0000000-0000-0000-0000-000000000001", "password_hash": DEV_PASSWORD_HASH},
        "marcus.rodriguez@pharmacorp.com": {"id": "b0000000-0000-0000-0000-000000000002", "name": "Marcus Rodriguez", "roles": ["analyst"], "org_id": "a0000000-0000-0000-0000-000000000001", "password_hash": DEV_PASSWORD_HASH},
        "lisa.park@medtech.com": {"id": "b0000000-0000-0000-0000-000000000003", "name": "Lisa Park", "roles": ["admin", "analyst"], "org_id": "a0000000-0000-0000-0000-000000000002", "password_hash": DEV_PASSWORD_HASH},
        "auditor@scirm.dev": {"id": "b0000000-0000-0000-0000-000000000004", "name": "SCIRM Auditor", "roles": ["auditor", "viewer"], "org_id": "default-org", "password_hash": DEV_PASSWORD_HASH},
    }

    user_info = dev_users.get(request.email)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Validate password
    if not verify_password(request.password, user_info["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(data={
        "sub": user_info["id"],
        "email": request.email,
        "name": user_info["name"],
        "roles": user_info["roles"],
        "org_id": user_info["org_id"],
    })

    return {"access_token": token, "token_type": "bearer"}

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
            return RiskAssessmentResponse(**response.json())
    
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
                f"{EXECUTOR_URL}/recommendations/{risk_id}",
                headers={"Authorization": f"Bearer {token.credentials}"},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    except httpx.HTTPError as e:
        logger.error("Failed to fetch recommendations", risk_id=risk_id, error=str(e))
        raise HTTPException(status_code=500, detail="Recommendation service unavailable")

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
