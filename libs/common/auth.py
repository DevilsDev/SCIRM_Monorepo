"""
SCIRM Authentication Utilities
JWT token verification and user management.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext

from .models import User

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthenticationError(Exception):
    """Authentication related errors."""
    pass

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def verify_token(token: str) -> User:
    """Verify JWT token and return user."""
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
    
    # In a real implementation, fetch user from database
    # For now, return a mock user
    user = User(
        id=user_id,
        email=payload.get("email", "user@example.com"),
        name=payload.get("name", "Test User"),
        roles=payload.get("roles", ["user"]),
        organization_id=payload.get("org_id", "default-org")
    )
    
    return user

def require_role(required_role: str):
    """Decorator to require specific role."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This would be implemented with dependency injection in FastAPI
            # For now, it's a placeholder
            return await func(*args, **kwargs)
        return wrapper
    return decorator
