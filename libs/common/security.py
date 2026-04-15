"""
SCIRM Shared Security Utilities
CORS configuration, rate limiting, and security headers.
"""

import os
import time
from collections import defaultdict
from typing import List

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware


def get_allowed_origins() -> List[str]:
    """
    Get CORS allowed origins from environment.
    In development, allows localhost. In production, restricts to configured origins.
    """
    env = os.getenv("ENVIRONMENT", "development")
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "")

    if configured:
        return [o.strip() for o in configured.split(",") if o.strip()]

    if env == "production":
        return [
            "https://scirm.company.com",
            "https://staging.scirm.company.com",
        ]

    # Development defaults
    return [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware with environment-appropriate origins."""
    origins = get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


class RateLimiter:
    """Simple in-memory rate limiter. Use Redis-backed solution in production."""

    def __init__(self, requests_per_minute: int = 100, burst: int = 200):
        self.rpm = requests_per_minute
        self.burst = burst
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, now: float) -> None:
        window = now - 60.0
        self._hits[key] = [t for t in self._hits[key] if t > window]

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        self._cleanup(client_ip, now)

        if len(self._hits[client_ip]) >= self.burst:
            return False

        self._hits[client_ip].append(now)
        return len(self._hits[client_ip]) <= self.rpm


def setup_rate_limiting(app: FastAPI, requests_per_minute: int = 100, burst: int = 200) -> None:
    """Add rate limiting middleware to a FastAPI app."""
    limiter = RateLimiter(requests_per_minute=requests_per_minute, burst=burst)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limiting for health/metrics endpoints
        if request.url.path in ("/health", "/ready", "/metrics"):
            return await call_next(request)

        if not limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
            )

        response = await call_next(request)
        return response
