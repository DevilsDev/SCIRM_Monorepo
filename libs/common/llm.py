"""
SCIRM Shared LLM Client

Providers:
- bedrock: Claude on Amazon Bedrock (Converse API). The default.
- anthropic, openai: direct APIs. These are only allowed when LLM_EU_ONLY=false.

EU-only mode (LLM_EU_ONLY, on by default) keeps every prompt inside the EU:
- Only Bedrock is used, and there is no fallback to another provider. A stray
  ANTHROPIC_API_KEY or OPENAI_API_KEY must not send supplier data elsewhere.
- The Bedrock region must be an EU region.
- The model ID must be an EU geo inference profile ("eu.") or a plain in-region
  model ID. "us.", "apac.", "global." and similar profiles route requests outside
  the EU even from an EU region, so they are refused.

Credentials for Bedrock come from the standard AWS chain (an IAM role, IRSA in
Kubernetes, or AWS_* environment variables), or a Bedrock API key in
AWS_BEARER_TOKEN_BEDROCK. They are never read from code or config files.
"""

import asyncio
import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional

import structlog

logger = structlog.get_logger()

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "bedrock")
LLM_EU_ONLY = os.getenv("LLM_EU_ONLY", "true").lower() == "true"
# Model per provider, so a fallback never sends one provider's model name to the other.
# LLM_MODEL, if set, overrides the primary provider's model only.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
LLM_MODEL = os.getenv("LLM_MODEL", "")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "eu-central-1"))
# EU geo inference profile, checked against the Bedrock model card (2026-10-20).
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-5-5")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "2"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_NON_EU_PROFILE_PREFIXES = ("us.", "us-gov.", "apac.", "au.", "jp.", "ca.", "global.")


def eu_model_allowed(model_id: str, region: str) -> Optional[str]:
    """Why this Bedrock model/region would send data outside the EU, or None if it would not."""
    if not region.startswith("eu-"):
        return f"region {region!r} is not an EU region"
    if model_id.startswith(_NON_EU_PROFILE_PREFIXES):
        return f"inference profile {model_id!r} routes outside the EU; use an 'eu.' profile"
    if "." not in model_id:
        return f"model id {model_id!r} is not a Bedrock model id"
    return None


# Per-request record of what the LLM actually did, so responses can report
# "LLM used" truthfully instead of "an API key is configured".
_usage: ContextVar[Optional[Dict[str, int]]] = ContextVar("llm_usage", default=None)


@contextmanager
def track_usage() -> Iterator[Dict[str, Any]]:
    """Count successful and failed LLM calls made inside this block, and the provider and
    model of the last successful one."""
    stats: Dict[str, Any] = {"calls": 0, "failures": 0}
    token = _usage.set(stats)
    try:
        yield stats
    finally:
        _usage.reset(token)


def _record(key: str, provider: Optional[str] = None, model: Optional[str] = None) -> None:
    stats = _usage.get()
    if stats is not None:
        stats[key] += 1
        if provider:  # which model answered, for the AI run log
            stats["provider"], stats["model"] = provider, model


# One client per provider: SDK clients hold connection pools and must be reused.
_clients: Dict[str, Any] = {}


def bedrock_client():
    """Shared bedrock-runtime client with explicit timeouts and adaptive retries."""
    if "bedrock" not in _clients:
        import boto3
        from botocore.config import Config
        _clients["bedrock"] = boto3.client(
            "bedrock-runtime", region_name=BEDROCK_REGION,
            config=Config(connect_timeout=5, read_timeout=LLM_TIMEOUT,
                          retries={"max_attempts": 3, "mode": "adaptive"}))
    return _clients["bedrock"]


_credential_check: Dict[str, Any] = {"at": 0.0, "present": False}


def _bedrock_credentials_present() -> bool:
    """Whether AWS credentials can be found. Cached for 5 minutes: without credentials,
    boto3 probes the instance metadata service, which takes about a second."""
    if os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        return True
    import time
    if time.monotonic() - _credential_check["at"] < 300:
        return _credential_check["present"]
    try:
        import boto3
        present = boto3.Session().get_credentials() is not None
    except Exception:
        present = False
    _credential_check.update(at=time.monotonic(), present=present)
    return present


def _get_openai_client():
    if "openai" not in _clients:
        from openai import AsyncOpenAI
        _clients["openai"] = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=LLM_TIMEOUT)
    return _clients["openai"]


def _get_anthropic_client():
    if "anthropic" not in _clients:
        from anthropic import AsyncAnthropic
        _clients["anthropic"] = AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=LLM_TIMEOUT)
    return _clients["anthropic"]


async def _call_bedrock(prompt: str, system: str, model: str) -> str:
    # No temperature: Claude 5.5 models on Bedrock run with adaptive thinking on by default.
    def call():
        return bedrock_client().converse(
            modelId=model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": LLM_MAX_TOKENS},
        )
    response = await asyncio.to_thread(call)
    blocks: List[Dict[str, Any]] = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(b.get("text", "") for b in blocks if "text" in b)
    if not text:
        raise RuntimeError("Bedrock returned no text content")
    return text


async def _call_openai(prompt: str, system: str, model: str) -> str:
    client = _get_openai_client()
    resp = await client.chat.completions.create(
        model=model,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content


async def _call_anthropic(prompt: str, system: str, model: str) -> str:
    client = _get_anthropic_client()
    resp = await client.messages.create(
        model=model,
        max_tokens=LLM_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


_CALLS = {"bedrock": _call_bedrock, "openai": _call_openai, "anthropic": _call_anthropic}


def _available(provider: str) -> bool:
    if provider == "bedrock":
        return _bedrock_credentials_present() and (not LLM_EU_ONLY or eu_model_allowed(BEDROCK_MODEL_ID, BEDROCK_REGION) is None)
    if LLM_EU_ONLY:
        return False  # direct APIs do not guarantee EU-only processing
    return bool({"openai": OPENAI_API_KEY, "anthropic": ANTHROPIC_API_KEY}.get(provider))


def _call_order(provider: str) -> List[str]:
    """Providers to try, in order. EU-only mode never falls back."""
    if LLM_EU_ONLY:
        return ["bedrock"] if provider == "bedrock" and _available("bedrock") else []
    order = [provider] + [p for p in ("anthropic", "openai") if p != provider]
    return [p for p in order if _available(p)]


def _model_for(provider: str, primary: str, override: Optional[str]) -> str:
    if override and provider == primary:
        return override
    return {"bedrock": BEDROCK_MODEL_ID, "openai": OPENAI_MODEL, "anthropic": ANTHROPIC_MODEL}[provider]


async def generate(
    prompt: str,
    system: str = "You are an expert supply chain risk analyst. Respond with valid JSON only.",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """Call the configured LLM and return the raw text response."""
    provider = provider or LLM_PROVIDER
    order = _call_order(provider)
    if not order:
        _record("failures")
        raise RuntimeError(f"No LLM provider available for {provider!r} (EU-only={LLM_EU_ONLY})")

    last_error = None
    for prov in order:
        resolved_model = _model_for(prov, provider, model or LLM_MODEL)
        if prov == "bedrock" and LLM_EU_ONLY:
            problem = eu_model_allowed(resolved_model, BEDROCK_REGION)
            if problem:
                raise RuntimeError(f"Refusing Bedrock call: {problem}")
        for attempt in range(1, LLM_RETRY_ATTEMPTS + 1):
            try:
                logger.info("LLM call", provider=prov, model=resolved_model, attempt=attempt)
                result = await _CALLS[prov](prompt, system, resolved_model)
                _record("calls", prov, resolved_model)
                return result
            except Exception as exc:
                last_error = exc
                # Error type only: messages can echo request content.
                logger.warning("LLM call failed", provider=prov, model=resolved_model, attempt=attempt,
                               error=type(exc).__name__)

    _record("failures")
    logger.error("All LLM providers failed", error=type(last_error).__name__ if last_error else None)
    raise RuntimeError(f"LLM generation failed after all retries: {type(last_error).__name__}")


async def generate_json(
    prompt: str,
    system: str = "You are an expert supply chain risk analyst. Respond with valid JSON only, no markdown fences.",
    **kwargs,
) -> Dict[str, Any]:
    """Call the LLM and parse the response as JSON."""
    raw = await generate(prompt, system=system, **kwargs)

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON, attempting repair", length=len(text))
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


def is_configured() -> bool:
    """Whether a call would reach a model under the current policy."""
    return bool(_call_order(LLM_PROVIDER))
