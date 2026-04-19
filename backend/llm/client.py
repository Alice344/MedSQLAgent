"""
Unified LLM client factory.

Supports:
  - OpenAI              (LLM_PROVIDER=openai)
  - Azure AI Serverless  (LLM_PROVIDER=azure_serverless)
    e.g. DeepSeek-V3, Llama, Phi via Azure AI Foundry
  - Anthropic Claude     (LLM_PROVIDER=anthropic)
    Uses Anthropic's OpenAI-compatible endpoint

Both use the OpenAI Python SDK — Azure Serverless and Anthropic endpoints
expose an OpenAI-compatible REST API, so only ``base_url`` and ``api_key`` differ.

Configuration lives in ``backend/.env`` (see ``.env.example``).
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Module-level singletons ──────────────────────────────────────────────────

_client: Optional[OpenAI] = None
_model: Optional[str] = None

# ── LLM response cache ──────────────────────────────────────────────────────
# Simple in-memory LRU cache keyed by hash(model + messages).
# Avoids redundant LLM calls for identical prompts (e.g. same user question).
_CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "1").strip().lower() not in ("0", "false", "no")
_CACHE_MAX_SIZE = int(os.getenv("LLM_CACHE_MAX_SIZE", "200"))
_cache: OrderedDict[str, str] = OrderedDict()


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


# ── Public API ───────────────────────────────────────────────────────────────


def get_llm_client() -> OpenAI:
    """Return a cached OpenAI-compatible client based on ``LLM_PROVIDER``."""
    global _client
    if _client is not None:
        return _client

    provider = _provider()

    if provider == "azure_serverless":
        endpoint = os.getenv("AZURE_AI_ENDPOINT", "").strip()
        api_key = os.getenv("AZURE_AI_API_KEY", "").strip()
        if not endpoint or not api_key:
            raise ValueError(
                "AZURE_AI_ENDPOINT and AZURE_AI_API_KEY are required "
                "when LLM_PROVIDER=azure_serverless"
            )
        base_url = endpoint.rstrip("/")
        # The OpenAI SDK expects a /v1 suffix
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        logger.info("LLM provider: Azure AI Serverless → %s", endpoint)
        _client = OpenAI(base_url=base_url, api_key=api_key)

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        logger.info("LLM provider: Anthropic Claude")
        _client = OpenAI(
            base_url="https://api.anthropic.com/v1/",
            api_key=api_key,
        )

    else:  # openai (default)
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        logger.info("LLM provider: OpenAI")
        _client = OpenAI(api_key=api_key)

    return _client


def get_model_name() -> str:
    """Return the model / deployment name to use for chat completions."""
    global _model
    if _model is not None:
        return _model

    provider = _provider()
    if provider == "azure_serverless":
        # Azure Serverless endpoints are model-specific; the server usually
        # ignores this parameter, but the SDK requires it.
        _model = os.getenv("AZURE_AI_MODEL", "deepseek-v3")
    elif provider == "anthropic":
        _model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    else:
        _model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    return _model


def reset_client() -> None:
    """Force re-creation on next call (e.g. after env vars change at runtime)."""
    global _client, _model
    _client = None
    _model = None


def chat_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 1000,
    response_format: Optional[Dict[str, Any]] = None,
) -> str:
    """Convenience: one-shot chat completion → text content."""
    resolved_model = model or get_model_name()

    # ── Cache lookup ─────────────────────────────────────────────────────
    cache_key = None
    if _CACHE_ENABLED and temperature <= 0.1:
        # Only cache (near-)deterministic calls
        raw = repr((resolved_model, messages, max_tokens, response_format))
        cache_key = hashlib.sha256(raw.encode()).hexdigest()
        if cache_key in _cache:
            logger.debug("LLM cache hit for %s", cache_key[:12])
            _cache.move_to_end(cache_key)  # refresh LRU position
            return _cache[cache_key]

    client = get_llm_client()
    kwargs: Dict[str, Any] = dict(
        model=resolved_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:
        err_msg = str(exc).lower()
        if "context_length" in err_msg or "token" in err_msg or "too long" in err_msg:
            raise RuntimeError(
                "The conversation is too long for the model's context window. "
                "Please start a new conversation."
            ) from exc
        raise RuntimeError(f"LLM call failed: {exc}") from exc
    result = (resp.choices[0].message.content or "").strip()

    # ── Cache store ──────────────────────────────────────────────────────
    if cache_key is not None:
        _cache[cache_key] = result
        if len(_cache) > _CACHE_MAX_SIZE:
            _cache.popitem(last=False)  # evict oldest

    return result
