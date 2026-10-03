"""Provider-neutral LLM client (Anthropic / Gemini / Groq / OpenRouter / custom).

Every caller in RootIQ treats the LLM as an optional *wording* layer:
`complete()` never raises and returns None when the LLM is disabled, missing a key,
slow, or broken — the caller then falls back to its deterministic answer.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.core.config import settings

log = logging.getLogger("rootiq.llm")

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini": "gemini-2.5-flash",
    "custom": "rootiq-network",  # your own fine-tuned model behind an OpenAI-compatible server
    "groq": "qwen/qwen3.8-27b",  # checked against GET /openai/v1/models on 2026-09-28; model ids change, re-check
    "openrouter": "openai/gpt-4o-mini",
}
PROVIDERS = tuple(DEFAULT_MODELS)


def _key(provider: str) -> str:
    return {
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
        "openrouter": settings.openrouter_api_key,
        "custom": settings.custom_llm_api_key,
    }.get(provider, "")


def model_name(provider: str | None = None) -> str:
    provider = provider or settings.llm_provider
    return settings.llm_model or DEFAULT_MODELS.get(provider, "")


def enabled() -> bool:
    if not settings.llm_enabled or settings.llm_provider not in PROVIDERS:
        return False
    if settings.llm_provider == "custom":  # local/private servers often need no key, but need an address
        return bool(settings.llm_base_url)
    return bool(_key(settings.llm_provider))


# Usage counters (per process) so operators can watch cost and reliability.
# Character counts are a cheap proxy for tokens (about 4 characters per token).
USAGE = {"calls": 0, "errors": 0, "rateLimited": 0, "skipped": 0, "totalMs": 0.0, "charsIn": 0, "charsOut": 0}
# After an HTTP 429 the provider is left alone for its Retry-After (capped), so we do not hammer it
# and callers get their deterministic fallback immediately instead of waiting on a failing call.
_cooldown_until = 0.0
MAX_COOLDOWN_S = 60.0


def usage() -> dict:
    calls = USAGE["calls"]
    return {
        **USAGE,
        "avgMs": round(USAGE["totalMs"] / calls, 1) if calls else 0.0,
        "approxTokensIn": USAGE["charsIn"] // 4,
        "approxTokensOut": USAGE["charsOut"] // 4,
        "cooldownSeconds": round(max(0.0, _cooldown_until - time.time()), 1),
    }


def info() -> dict:
    """Safe-to-expose LLM status (never includes keys)."""
    return {
        "enabled": enabled(),
        "provider": settings.llm_provider,
        "model": model_name(),
        "requested": bool(settings.llm_enabled),
        "usage": usage(),
    }


async def _post(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def _anthropic(system: str, user: str, max_tokens: int, timeout: float) -> str:
    data = await _post(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        {
            "model": model_name("anthropic"),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout,
    )
    return "".join(b.get("text", "") for b in data["content"])


async def _gemini(system: str, user: str, max_tokens: int, timeout: float) -> str:
    data = await _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name('gemini')}:generateContent",
        {"x-goog-api-key": settings.gemini_api_key, "content-type": "application/json"},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.1},
        },
        timeout,
    )
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


async def _groq(system: str, user: str, max_tokens: int, timeout: float) -> str:
    data = await _post(
        "https://api.groq.com/openai/v1/chat/completions",
        {
            "authorization": f"Bearer {settings.groq_api_key}",
            "content-type": "application/json",
        },
        {
            "model": model_name("groq"),
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout,
    )
    return data["choices"][0]["message"]["content"]


async def _custom(system: str, user: str, max_tokens: int, timeout: float) -> str:
    headers = {"content-type": "application/json"}
    if settings.custom_llm_api_key:
        headers["authorization"] = f"Bearer {settings.custom_llm_api_key}"
    data = await _post(
        settings.llm_base_url.rstrip("/") + "/chat/completions",
        headers,
        {
            "model": model_name("custom"),
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout,
    )
    return data["choices"][0]["message"]["content"]


async def _openrouter(system: str, user: str, max_tokens: int, timeout: float) -> str:
    data = await _post(
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "authorization": f"Bearer {settings.openrouter_api_key}",
            "content-type": "application/json",
            "HTTP-Referer": "https://rootiq.local",
            "X-Title": "RootIQ Copilot",
        },
        {
            "model": model_name("openrouter"),
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout,
    )
    return data["choices"][0]["message"]["content"]


_IMPL = {
    "anthropic": _anthropic,
    "gemini": _gemini,
    "groq": _groq,
    "custom": _custom,
    "openrouter": _openrouter,
}


async def complete(
    system: str, user: str, max_tokens: int = 300, timeout: float = 6.0
) -> str | None:
    global _cooldown_until
    if not enabled():
        return None
    if time.time() < _cooldown_until:
        USAGE["skipped"] += 1
        return None
    t0 = time.perf_counter()
    USAGE["calls"] += 1
    USAGE["charsIn"] += len(system) + len(user)
    try:
        text = await _IMPL[settings.llm_provider](system, user, max_tokens, timeout)
    except Exception as e:
        USAGE["errors"] += 1
        resp = getattr(e, "response", None)
        if getattr(resp, "status_code", None) == 429:
            USAGE["rateLimited"] += 1
            try:
                wait = float(resp.headers.get("retry-after", 20))
            except ValueError:
                wait = 20.0
            _cooldown_until = time.time() + min(max(wait, 1.0), MAX_COOLDOWN_S)
        detail = getattr(resp, "text", "")[:200]
        log.warning("LLM call failed (%s): %s %s", settings.llm_provider, type(e).__name__, detail or e)
        return None
    finally:
        USAGE["totalMs"] += (time.perf_counter() - t0) * 1000
    text = (text or "").strip()
    USAGE["charsOut"] += len(text)
    return text or None
