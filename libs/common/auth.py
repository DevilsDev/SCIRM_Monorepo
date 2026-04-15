"""
SCIRM Authentication Utilities
JWT tokens, password hashing, MFA (TOTP), role enforcement, and service-to-service auth.
"""

import hashlib
import hmac
import os
import struct
import time
import base64
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from passlib.context import CryptContext

from .models import User

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_default_secret = os.getenv("JWT_SECRET_KEY", "")
if not _default_secret:
    import warnings
    warnings.warn(
        "JWT_SECRET_KEY is not set — using an insecure default. "
        "Set JWT_SECRET_KEY in your environment for production.",
        stacklevel=2,
    )
    _default_secret = "INSECURE-DEV-ONLY-CHANGE-ME"

SECRET_KEY = _default_secret
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
MFA_ENABLED = os.getenv("MFA_ENABLED", "false").lower() == "true"
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "scirm-internal-dev-key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

class AuthenticationError(Exception):
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a longer-lived refresh token (30 days)."""
    return create_access_token(
        data={"sub": user_id, "type": "refresh"},
        expires_delta=timedelta(days=30),
    )


async def verify_token(token: str) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    return User(
        id=user_id,
        email=payload.get("email", "user@example.com"),
        name=payload.get("name", "Test User"),
        roles=payload.get("roles", ["user"]),
        organization_id=payload.get("org_id", "default-org"),
    )


# ---------------------------------------------------------------------------
# MFA — TOTP (RFC 6238)
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Generate a random base32-encoded TOTP secret."""
    return base64.b32encode(os.urandom(20)).decode("utf-8")


def get_totp_uri(secret: str, email: str, issuer: str = "SCIRM") -> str:
    """Generate an otpauth:// URI for authenticator apps."""
    return f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}&digits=6&period=30"


def generate_totp(secret: str, time_step: int = 30) -> str:
    """Generate a 6-digit TOTP code for the current time window."""
    key = base64.b32decode(secret, casefold=True)
    counter = int(time.time()) // time_step
    counter_bytes = struct.pack(">Q", counter)
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = hmac_hash[-1] & 0x0F
    code = struct.unpack(">I", hmac_hash[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10**6).zfill(6)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """
    Verify a TOTP code with a time window tolerance.
    window=1 allows codes from the previous, current, and next 30-second intervals.
    """
    for offset in range(-window, window + 1):
        key = base64.b32decode(secret, casefold=True)
        counter = (int(time.time()) // 30) + offset
        counter_bytes = struct.pack(">Q", counter)
        hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        off = hmac_hash[-1] & 0x0F
        expected = struct.unpack(">I", hmac_hash[off:off + 4])[0] & 0x7FFFFFFF
        if code == str(expected % 10**6).zfill(6):
            return True
    return False


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------

def require_role(*required_roles: str):
    """
    FastAPI dependency that enforces role-based access.
    Usage: Depends(require_role("admin", "analyst"))
    """
    async def role_checker(request: Request, token=Depends(security)):
        user = await verify_token(token.credentials)
        if not any(role in user.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(required_roles)}",
            )
        request.state.user = user
        return user
    return role_checker


def require_any_role():
    """FastAPI dependency that just verifies the token and extracts the user."""
    async def auth_checker(request: Request, token=Depends(security)):
        user = await verify_token(token.credentials)
        request.state.user = user
        return user
    return auth_checker


# ---------------------------------------------------------------------------
# Service-to-service authentication (Zero Trust)
# ---------------------------------------------------------------------------

def verify_service_key(request: Request) -> bool:
    """
    Verify that the request contains a valid internal service API key.
    Used for agent-to-agent communication in production.
    """
    key = request.headers.get("X-Service-Key", "")
    if not key:
        return True  # Skip in dev when no key is configured
    return hmac.compare_digest(key, SERVICE_API_KEY)


def require_service_auth():
    """FastAPI dependency for service-to-service endpoints."""
    async def service_checker(request: Request):
        env = os.getenv("ENVIRONMENT", "development")
        if env == "production":
            key = request.headers.get("X-Service-Key", "")
            if not key or not hmac.compare_digest(key, SERVICE_API_KEY):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or missing service API key",
                )
    return service_checker
