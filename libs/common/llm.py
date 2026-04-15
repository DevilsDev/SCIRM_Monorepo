"""
SCIRM Shared LLM Client
Unified interface for OpenAI and Anthropic with automatic fallback,
structured JSON output, and retry logic.
"""

import json
import os
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4-turbo-preview")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "2"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def _get_openai_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=LLM_TIMEOUT)


def _get_anthropic_client():
    from anthropic import AsyncAnthropic
    return AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=LLM_TIMEOUT)


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


async def generate(
    prompt: str,
    system: str = "You are an expert supply chain risk analyst. Respond with valid JSON only.",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Call the configured LLM and return the raw text response.
    Falls back to the other provider if the primary fails.
    """
    provider = provider or LLM_PROVIDER
    model = model or LLM_MODEL

    providers = {
        "openai": (_call_openai, model if "gpt" in model else "gpt-4-turbo-preview"),
        "anthropic": (_call_anthropic, model if "claude" in model else "claude-3-5-sonnet-20241022"),
    }

    # Build ordered call list: primary first, then fallback
    order = [provider]
    fallback = "anthropic" if provider == "openai" else "openai"
    if providers.get(fallback):
        order.append(fallback)

    last_error = None
    for prov in order:
        call_fn, resolved_model = providers.get(prov, (None, None))
        if not call_fn:
            continue

        for attempt in range(1, LLM_RETRY_ATTEMPTS + 1):
            try:
                logger.info("LLM call", provider=prov, model=resolved_model, attempt=attempt)
                result = await call_fn(prompt, system, resolved_model)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM call failed",
                    provider=prov,
                    model=resolved_model,
                    attempt=attempt,
                    error=str(exc),
                )

    logger.error("All LLM providers failed", error=str(last_error))
    raise RuntimeError(f"LLM generation failed after all retries: {last_error}")


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
        logger.warning("LLM returned invalid JSON, attempting repair", raw=text[:200])
        # Try to extract JSON object from the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


def is_configured() -> bool:
    """Check if at least one LLM provider has an API key configured."""
    return bool(OPENAI_API_KEY) or bool(ANTHROPIC_API_KEY)
