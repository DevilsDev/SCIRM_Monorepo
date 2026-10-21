"""
Encryption at rest for small secrets: the TOTP seed behind MFA, and the password of a
tenant's ERP connection (libs/integrations/sap_odata.py).

AES-256-GCM with a random 96-bit nonce. What the secret belongs to is bound in as
associated data: the user's id for an MFA seed, "erp:<system>:<org>:<connection id>"
for an ERP password. A ciphertext copied onto another account, tenant or connection
therefore fails to decrypt. Stored form:

    enc:v1:<base64url(nonce || ciphertext || tag)>

Keys (32 random bytes, base64url), e.g. `python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`:
- MFA_ENCRYPTION_KEY: encrypts, and is tried first when decrypting. (The name predates
  ERP connections; the one key protects both kinds of secret.)
- MFA_ENCRYPTION_KEY_PREVIOUS (optional): still decrypts, for key rotation. Values are
  re-encrypted with the current key as they are read (see libs/common/store.py).

Outside development the key is required: require_key() raises at gateway start-up.
In development a fixed, publicly known key is used (with a warning), so local
accounts keep working across restarts; it protects nothing and is never used elsewhere.
MFA seeds stored before encryption have no prefix: decrypt() returns them as-is and
reports them, so the caller can re-encrypt them. ERP passwords were never stored in
plaintext, so their callers pass allow_plaintext=False.
"""

import base64
import hashlib
import os
import warnings
from typing import List, Optional, Tuple

# Read directly (not from libs.common.auth), so importing the store never requires the
# JWT secret in services that do not issue tokens.
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_DEV = ENVIRONMENT in {"development", "dev", "local", "test"}

PREFIX = "enc:v1:"
_DEV_KEY = hashlib.sha256(b"scirm-development-only-mfa-key").digest()


class SecretBoxError(RuntimeError):
    pass


def _decode_key(value: str, name: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.strip() + "=" * (-len(value.strip()) % 4))
    except ValueError as exc:
        raise SecretBoxError(f"{name} is not valid base64") from exc
    if len(key) != 32:
        raise SecretBoxError(f"{name} must be 32 bytes (base64url), got {len(key)}")
    return key


def _keys() -> List[bytes]:
    current = os.getenv("MFA_ENCRYPTION_KEY", "")
    if current:
        keys = [_decode_key(current, "MFA_ENCRYPTION_KEY")]
    elif IS_DEV:
        warnings.warn("MFA_ENCRYPTION_KEY is not set: using the development-only key.", stacklevel=3)
        keys = [_DEV_KEY]
    else:
        raise SecretBoxError(f"MFA_ENCRYPTION_KEY must be set when ENVIRONMENT={ENVIRONMENT!r}.")
    previous = os.getenv("MFA_ENCRYPTION_KEY_PREVIOUS", "")
    if previous:
        keys.append(_decode_key(previous, "MFA_ENCRYPTION_KEY_PREVIOUS"))
    return keys


def require_key() -> None:
    """Fail closed at start-up rather than at the first MFA sign-in or ERP import."""
    _keys()


def encrypt(plaintext: str, bound_to: str) -> str:
    """Seal `plaintext`; it only opens again with the same `bound_to` (associated data)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    sealed = AESGCM(_keys()[0]).encrypt(nonce, plaintext.encode("utf-8"), str(bound_to).encode("utf-8"))
    return PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii").rstrip("=")


def decrypt(stored: Optional[str], bound_to: str, allow_plaintext: bool = True) -> Tuple[Optional[str], bool]:
    """(plaintext, needs_reencryption). needs_reencryption is True for legacy plaintext
    and for values sealed with the previous key."""
    if not stored:
        return stored, False
    if not stored.startswith(PREFIX):
        if not allow_plaintext:
            raise SecretBoxError("stored secret is not encrypted")
        return stored, True
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    body = stored[len(PREFIX):]
    raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    nonce, sealed = raw[:12], raw[12:]
    for index, key in enumerate(_keys()):
        try:
            plaintext = AESGCM(key).decrypt(nonce, sealed, str(bound_to).encode("utf-8")).decode("utf-8")
            return plaintext, index > 0
        except InvalidTag:
            continue
    raise SecretBoxError("stored secret cannot be decrypted with MFA_ENCRYPTION_KEY or MFA_ENCRYPTION_KEY_PREVIOUS")
