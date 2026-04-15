"""
SCIRM OAuth 2.0 / OpenID Connect Integration
Supports Google, Azure AD, and generic OIDC providers.
"""

import os
import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import structlog

logger = structlog.get_logger()

# Provider configurations loaded from environment
OAUTH_PROVIDERS: Dict[str, Dict[str, str]] = {
    "google": {
        "client_id": os.getenv("OAUTH_GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("OAUTH_GOOGLE_CLIENT_SECRET", ""),
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": "openid email profile",
    },
    "azure": {
        "client_id": os.getenv("OAUTH_AZURE_CLIENT_ID", ""),
        "client_secret": os.getenv("OAUTH_AZURE_CLIENT_SECRET", ""),
        "tenant_id": os.getenv("OAUTH_AZURE_TENANT_ID", "common"),
        "authorize_url": f"https://login.microsoftonline.com/{os.getenv('OAUTH_AZURE_TENANT_ID', 'common')}/oauth2/v2.0/authorize",
        "token_url": f"https://login.microsoftonline.com/{os.getenv('OAUTH_AZURE_TENANT_ID', 'common')}/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
        "scopes": "openid email profile",
    },
}


def get_authorization_url(
    provider: str,
    redirect_uri: str,
    state: Optional[str] = None,
) -> Dict[str, str]:
    """Generate OAuth authorization URL for the given provider."""
    config = OAUTH_PROVIDERS.get(provider)
    if not config or not config.get("client_id"):
        return {
            "error": f"Provider '{provider}' not configured. Set OAUTH_{provider.upper()}_CLIENT_ID in environment.",
            "provider": provider,
        }

    state = state or secrets.token_urlsafe(32)

    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scopes"],
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    url = f"{config['authorize_url']}?{urlencode(params)}"
    return {"authorization_url": url, "state": state, "provider": provider}


async def exchange_code(
    provider: str,
    code: str,
    redirect_uri: str,
) -> Dict[str, Any]:
    """Exchange authorization code for tokens and user info."""
    config = OAUTH_PROVIDERS.get(provider)
    if not config or not config.get("client_id"):
        raise ValueError(f"Provider '{provider}' not configured")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            config["token_url"],
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()

        # Fetch user info
        userinfo_response = await client.get(
            config["userinfo_url"],
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    return {
        "access_token": tokens.get("access_token"),
        "id_token": tokens.get("id_token"),
        "refresh_token": tokens.get("refresh_token"),
        "user": {
            "email": userinfo.get("email"),
            "name": userinfo.get("name"),
            "picture": userinfo.get("picture"),
            "provider": provider,
            "provider_id": userinfo.get("sub"),
        },
    }


def get_available_providers() -> list:
    """Return list of configured OAuth providers."""
    return [
        {"provider": name, "configured": bool(config.get("client_id"))}
        for name, config in OAUTH_PROVIDERS.items()
    ]
