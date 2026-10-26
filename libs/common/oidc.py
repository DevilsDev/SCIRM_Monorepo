"""
OpenID Connect (authorization code flow with PKCE) against a tenant's identity provider.

The issuer, client id and client secret are entered by a tenant admin, so every server-side
request (discovery document, key set, token endpoint) goes through the outbound guard
(libs/common/outbound.py): outside development https only, public addresses only, pinned
to the checked address, no redirects followed, small responses, short timeouts.

ID tokens are accepted only when signed with an asymmetric algorithm (RS/PS/ES) by a key
from the provider's key set, issued by the configured issuer for this client, unexpired,
and carrying the nonce sent with the request. Multi-tenant issuers (Microsoft Entra
/common, /organizations, /consumers) are refused: anyone can create a tenant there and
put any email in it.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlsplit

import httpx
import jwt

from libs.common import outbound

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
STRICT = _ENVIRONMENT not in {"development", "dev", "local", "test"}
ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512")
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_BYTES = 1024 * 1024
CACHE_SECONDS = 3600
LEEWAY = 60
_MULTI_TENANT = ("/common", "/organizations", "/consumers")

# Code-only hooks for tests: an httpx transport, and the DNS resolver.
transport_factory: Optional[Callable[[], httpx.AsyncBaseTransport]] = None
resolve: Callable[[str, int], List[str]] = outbound.system_resolve
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


class OidcError(Exception):
    """A sign-in or configuration failure; .reason is a short code for the audit log."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def validate_issuer(issuer: str, strict: Optional[bool] = None) -> str:
    strict = STRICT if strict is None else strict
    issuer = (issuer or "").strip()
    parts = urlsplit(issuer)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise OidcError("bad_issuer", "The issuer must be a URL, e.g. https://login.example.com/realms/acme.")
    if strict and parts.scheme != "https":
        raise OidcError("bad_issuer", "The issuer must use https://.")
    if parts.query or parts.fragment or parts.username or parts.password:
        raise OidcError("bad_issuer", "The issuer must not contain credentials, a query or a fragment.")
    path = parts.path.rstrip("/").lower()
    if any(path == m or path.startswith(m + "/") for m in _MULTI_TENANT):
        raise OidcError("multi_tenant_issuer", "Use your organization's own (tenant-specific) issuer, not a "
                                               "multi-tenant one such as /common or /organizations.")
    return issuer


async def _request(method: str, url: str, strict: bool, **kwargs: Any) -> Dict[str, Any]:
    parts = urlsplit(url)
    if strict and parts.scheme != "https":
        raise OidcError("insecure_endpoint", "The identity provider must use https://.")
    try:
        import asyncio
        target, sni = await asyncio.to_thread(outbound.pin, url, strict, resolve)
    except outbound.OutboundError as exc:
        raise OidcError("unreachable", f"The identity provider host {exc.host} "
                                       f"{'could not be found' if exc.kind == 'dns' else 'is not a public address'}.")
    headers = {"Accept": "application/json", **kwargs.pop("headers", {})}
    if sni:
        headers["Host"] = parts.netloc
    options: Dict[str, Any] = {"timeout": TIMEOUT, "follow_redirects": False}
    if transport_factory is not None:
        options["transport"] = transport_factory()
    try:
        async with httpx.AsyncClient(**options) as client:
            async with client.stream(method, target, headers=headers, extensions={"sni_hostname": sni} if sni else {},
                                     **kwargs) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise OidcError("too_large", "The identity provider sent too large a response.")
                status = response.status_code
    except httpx.HTTPError as exc:
        raise OidcError("unreachable", f"Could not reach the identity provider ({type(exc).__name__}).")
    try:
        data = json.loads(bytes(body))
    except ValueError:
        data = None
    if status != 200 or not isinstance(data, dict):
        error = data.get("error") if isinstance(data, dict) else None
        raise OidcError("provider_error", f"The identity provider answered HTTP {status}"
                                          + (f" ({error})" if error else "") + ".")
    return data


async def discover(issuer: str, strict: Optional[bool] = None) -> Dict[str, Any]:
    """The provider's metadata. Its issuer must equal the configured one exactly."""
    strict = STRICT if strict is None else strict
    cached = _cache.get(f"disc:{issuer}")
    if cached and cached[0] > time.time():
        return cached[1]
    doc = await _request("GET", issuer.rstrip("/") + "/.well-known/openid-configuration", strict)
    if doc.get("issuer") != issuer:
        raise OidcError("issuer_mismatch", f"The provider says its issuer is {doc.get('issuer')!r}, "
                                           f"not {issuer!r}. Enter the issuer exactly as it states it.")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not isinstance(doc.get(key), str):
            raise OidcError("bad_discovery", f"The provider's metadata has no {key}.")
        if strict and not doc[key].startswith("https://"):
            raise OidcError("insecure_endpoint", f"The provider's {key} must use https://.")
    _cache[f"disc:{issuer}"] = (time.time() + CACHE_SECONDS, doc)
    return doc


async def _keys(jwks_uri: str, strict: bool, refresh: bool = False) -> List[Dict[str, Any]]:
    cached = _cache.get(f"jwks:{jwks_uri}")
    if cached and cached[0] > time.time() and not refresh:
        return cached[1]["keys"]
    doc = await _request("GET", jwks_uri, strict)
    if not isinstance(doc.get("keys"), list):
        raise OidcError("bad_jwks", "The provider's key set is not valid.")
    _cache[f"jwks:{jwks_uri}"] = (time.time() + CACHE_SECONDS, doc)
    return doc["keys"]


def pkce_pair() -> Tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def authorization_url(doc: Dict[str, Any], client_id: str, redirect_uri: str, state: str, nonce: str,
                      code_challenge: str, login_hint: Optional[str] = None, fresh_login: bool = False) -> str:
    """fresh_login: the user must authenticate again now, even with a session at the
    identity provider (prompt=login, max_age=0); used for electronic signatures, which then
    check the ID token's auth_time."""
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
              "scope": "openid email profile", "state": state, "nonce": nonce,
              "code_challenge": code_challenge, "code_challenge_method": "S256",
              # query, not form_post: a cross-site POST would not carry the SameSite=Lax cookie.
              "response_mode": "query"}
    if login_hint:
        params["login_hint"] = login_hint
    if fresh_login:
        params.update(prompt="login", max_age="0")
    endpoint = doc["authorization_endpoint"]
    return endpoint + ("&" if "?" in endpoint else "?") + urlencode(params)


async def exchange_code(doc: Dict[str, Any], client_id: str, client_secret: str, code: str, verifier: str,
                        redirect_uri: str, strict: Optional[bool] = None) -> Dict[str, Any]:
    strict = STRICT if strict is None else strict
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return await _request("POST", doc["token_endpoint"], strict, headers={"Authorization": f"Basic {basic}"},
                          data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                                "code_verifier": verifier})


async def verify_id_token(id_token: str, doc: Dict[str, Any], client_id: str, nonce: str,
                          strict: Optional[bool] = None) -> Dict[str, Any]:
    """The verified claims, or OidcError."""
    strict = STRICT if strict is None else strict
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise OidcError("bad_token", "The identity provider sent an unreadable ID token.")
    alg, kid = header.get("alg"), header.get("kid")
    if alg not in ALGORITHMS:
        raise OidcError("bad_algorithm", f"ID tokens signed with {alg!r} are not accepted.")
    key = None
    for refresh in (False, True):  # an unknown key id: fetch the key set once more (rotation)
        keys = await _keys(doc["jwks_uri"], strict, refresh=refresh)
        match = [k for k in keys if (kid is None or k.get("kid") == kid) and k.get("use", "sig") == "sig"]
        if match:
            key = match[0]
            break
    if key is None:
        raise OidcError("unknown_key", "The ID token was signed with a key the provider does not publish.")
    try:
        claims = jwt.decode(id_token, jwt.PyJWK(key, algorithm=alg).key, algorithms=[alg], audience=client_id,
                            issuer=doc["issuer"], leeway=LEEWAY, options={"require": ["exp", "iat", "sub", "iss", "aud"]})
    except jwt.PyJWTError as exc:
        raise OidcError("invalid_token", f"The ID token was rejected ({type(exc).__name__}).")
    audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
    if len(audiences) > 1 and claims.get("azp") != client_id:
        raise OidcError("invalid_token", "The ID token was issued to another client.")
    if not secrets.compare_digest(str(claims.get("nonce") or ""), nonce):
        raise OidcError("bad_nonce", "The ID token does not belong to this sign-in.")
    return claims


def email_from(claims: Dict[str, Any]) -> Optional[str]:
    """The verified email to link an account the first time, or None."""
    if claims.get("email_verified") is False:
        return None
    email = claims.get("email")
    return email.strip().lower() if isinstance(email, str) and "@" in email else None
