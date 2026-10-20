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

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from .models import User

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DEV_ENVIRONMENTS = {"development", "dev", "local", "test"}
IS_DEV = ENVIRONMENT in DEV_ENVIRONMENTS

_default_secret = os.getenv("JWT_SECRET_KEY", "")
if not _default_secret:
    if not IS_DEV:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be set when ENVIRONMENT={ENVIRONMENT!r}."
        )
    import warnings
    warnings.warn(
        "JWT_SECRET_KEY is not set — using a random per-process secret. "
        "Tokens will be invalidated on restart.",
        stacklevel=2,
    )
    # Random rather than a fixed string, so tokens can never be forged from public source.
    _default_secret = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
elif len(_default_secret) < 32 and not IS_DEV:
    raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters.")

SECRET_KEY = _default_secret
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Short-lived access tokens: the frontend refreshes them silently with the 30-day refresh
# token, and refresh rejects deactivated accounts, so deactivation takes effect within this
# window. JWT_EXPIRATION_HOURS is still honoured if set explicitly.
ACCESS_TOKEN_EXPIRE_MINUTES = (int(os.environ["JWT_EXPIRATION_HOURS"]) * 60 if os.getenv("JWT_EXPIRATION_HOURS")
                               else int(os.getenv("JWT_EXPIRATION_MINUTES", "60")))
MFA_ENABLED = os.getenv("MFA_ENABLED", "false").lower() == "true"
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")

# Token types — verify_token only accepts "access"; refresh and mfa_pending
# tokens must never be usable as bearer credentials.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_MFA_PENDING = "mfa_pending"

# Roles allowed to create or modify data. Everyone else (viewer, auditor) is read-only.
WRITE_ROLES = ("admin", "analyst")

security = HTTPBearer()


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

class AuthenticationError(Exception):
    pass


# bcrypt only uses the first 72 bytes and bcrypt>=5 rejects longer input outright.
MAX_PASSWORD_BYTES = 72


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password = plain_password.encode("utf-8")
    if len(password) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(password, hashed_password.encode("utf-8"))
    except ValueError:
        return False  # Malformed stored hash


def get_password_hash(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    to_encode.setdefault("type", TOKEN_TYPE_ACCESS)
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a longer-lived refresh token (30 days)."""
    return create_access_token(
        data={"sub": user_id, "type": TOKEN_TYPE_REFRESH},
        expires_delta=timedelta(days=30),
    )


def decode_token(token: str, expected_type: str) -> dict:
    """Decode and validate a JWT, rejecting it unless its type claim matches."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise credentials_exception
    if payload.get("type") != expected_type:
        raise credentials_exception
    return payload


async def verify_token(token: str) -> User:
    payload = decode_token(token, TOKEN_TYPE_ACCESS)
    # Access tokens are always minted with identity claims; never fill in defaults,
    # which would silently place a user in a shared tenant or role.
    if not payload.get("org_id") or not isinstance(payload.get("roles"), list):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return User(
        id=payload["sub"],
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        roles=payload["roles"],
        organization_id=payload["org_id"],
    )


def require_write_access(user: User) -> None:
    """Raise 403 unless the user holds a role that may create or modify data."""
    if not any(role in WRITE_ROLES for role in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is read-only",
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
    key = base64.b32decode(secret, casefold=True)
    matched = False
    for offset in range(-window, window + 1):
        counter = (int(time.time()) // 30) + offset
        counter_bytes = struct.pack(">Q", counter)
        hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        off = hmac_hash[-1] & 0x0F
        expected = struct.unpack(">I", hmac_hash[off:off + 4])[0] & 0x7FFFFFFF
        # Constant-time compare; check every window so timing doesn't reveal which matched.
        if hmac.compare_digest(code.encode(), str(expected % 10**6).zfill(6).encode()):
            matched = True
    return matched


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
    if not SERVICE_API_KEY:
        return IS_DEV  # No key configured: only tolerated in development
    key = request.headers.get("X-Service-Key", "")
    return bool(key) and hmac.compare_digest(key, SERVICE_API_KEY)


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
