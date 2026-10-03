import pytest

from app.core.config import settings
from app.llm import client


def enable(monkeypatch, provider, key_attr):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "llm_model", "")
    monkeypatch.setattr(settings, key_attr, "test-key")


def test_disabled_by_default_and_info_never_leaks_keys(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    info = client.info()
    assert info["enabled"] is False
    assert "key" not in str(info).lower()


def test_enabled_requires_a_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert client.enabled() is False


def test_unknown_provider_is_disabled(monkeypatch):
    enable(monkeypatch, "anthropic", "anthropic_api_key")
    monkeypatch.setattr(settings, "llm_provider", "made-up")
    assert client.enabled() is False


def test_default_models_and_override(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "")
    assert client.model_name("groq") == client.DEFAULT_MODELS["groq"]
    monkeypatch.setattr(settings, "llm_model", "custom-1")
    assert client.model_name("gemini") == "custom-1"


@pytest.mark.asyncio
async def test_disabled_returns_none_without_network(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)

    async def boom(*a, **k):
        raise AssertionError("network must not be touched when disabled")

    monkeypatch.setattr(client, "_post", boom)
    assert await client.complete("s", "u") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,key_attr,reply,check",
    [
        ("anthropic", "anthropic_api_key", {"content": [{"type": "text", "text": "hi from claude"}]},
         lambda url, h, p: "anthropic.com" in url and h["x-api-key"] == "test-key" and p["system"] == "SYS"),
        ("gemini", "gemini_api_key", {"candidates": [{"content": {"parts": [{"text": "hi from gemini"}]}}]},
         lambda url, h, p: "generativelanguage" in url and h["x-goog-api-key"] == "test-key"
         and p["systemInstruction"]["parts"][0]["text"] == "SYS"),
        ("groq", "groq_api_key", {"choices": [{"message": {"content": "hi from groq"}}]},
         lambda url, h, p: "groq.com" in url and h["authorization"] == "Bearer test-key"
         and p["messages"][0] == {"role": "system", "content": "SYS"}),
        ("openrouter", "openrouter_api_key", {"choices": [{"message": {"content": "hi from openrouter"}}]},
         lambda url, h, p: "openrouter.ai" in url and h["authorization"] == "Bearer test-key"
         and p["messages"][0] == {"role": "system", "content": "SYS"}),
    ],
)
async def test_each_provider_builds_the_right_request(monkeypatch, provider, key_attr, reply, check):
    enable(monkeypatch, provider, key_attr)
    seen = {}

    async def fake_post(url, headers, payload, timeout):
        seen.update(url=url, headers=headers, payload=payload)
        return reply

    monkeypatch.setattr(client, "_post", fake_post)
    out = await client.complete("SYS", "USER")
    assert out and out.startswith("hi from")
    assert check(seen["url"], seen["headers"], seen["payload"])


@pytest.mark.asyncio
async def test_provider_errors_fall_back_to_none(monkeypatch):
    enable(monkeypatch, "groq", "groq_api_key")

    async def fail(*a, **k):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(client, "_post", fail)
    assert await client.complete("s", "u") is None


@pytest.mark.asyncio
async def test_usage_counters_track_calls_errors_and_size(monkeypatch):
    enable(monkeypatch, "groq", "groq_api_key")
    monkeypatch.setattr(client, "USAGE", {"calls": 0, "errors": 0, "rateLimited": 0, "skipped": 0, "totalMs": 0.0, "charsIn": 0, "charsOut": 0})

    async def ok(*a, **k):
        return {"choices": [{"message": {"content": "answer"}}]}

    async def fail(*a, **k):
        raise RuntimeError("500")

    monkeypatch.setattr(client, "_post", ok)
    await client.complete("sys", "user prompt")
    monkeypatch.setattr(client, "_post", fail)
    await client.complete("sys", "user prompt")
    u = client.usage()
    assert u["calls"] == 2 and u["errors"] == 1 and u["charsIn"] == 2 * len("sysuser prompt") and u["charsOut"] == len("answer")
    assert client.info()["usage"]["calls"] == 2 and "key" not in str(client.info()).lower()


@pytest.mark.asyncio
async def test_rate_limit_starts_a_cooldown_and_skips_calls_until_it_ends(monkeypatch):
    import httpx

    enable(monkeypatch, "groq", "groq_api_key")
    monkeypatch.setattr(client, "USAGE", {"calls": 0, "errors": 0, "rateLimited": 0, "skipped": 0, "totalMs": 0.0, "charsIn": 0, "charsOut": 0})
    monkeypatch.setattr(client, "_cooldown_until", 0.0)
    calls = []

    async def limited(url, headers, payload, timeout):
        calls.append(1)
        req = httpx.Request("POST", url)
        raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, headers={"retry-after": "7"}, request=req, text="rate limit"))

    monkeypatch.setattr(client, "_post", limited)
    assert await client.complete("s", "u") is None
    assert client.usage()["rateLimited"] == 1 and 5 < client.usage()["cooldownSeconds"] <= 7
    assert await client.complete("s", "u") is None  # skipped: the provider is not called during the cooldown
    assert len(calls) == 1 and client.usage()["skipped"] == 1

    monkeypatch.setattr(client, "_cooldown_until", 0.0)  # cooldown over
    assert await client.complete("s", "u") is None
    assert len(calls) == 2


def test_custom_provider_needs_an_address_not_a_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "custom")
    monkeypatch.setattr(settings, "llm_base_url", "")
    assert client.enabled() is False
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434/v1")
    assert client.enabled() is True
    assert "localhost" not in str(client.info())  # the address is never exposed by the status endpoint


@pytest.mark.asyncio
@pytest.mark.parametrize("key,expect_auth", [("", False), ("secret-token", True)])
async def test_custom_provider_uses_the_openai_compatible_shape(monkeypatch, key, expect_auth):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "custom")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434/v1/")
    monkeypatch.setattr(settings, "llm_model", "rootiq-network-v1")
    monkeypatch.setattr(settings, "custom_llm_api_key", key)
    seen = {}

    async def fake_post(url, headers, payload, timeout):
        seen.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": "hello from my model"}}]}

    monkeypatch.setattr(client, "_post", fake_post)
    assert await client.complete("SYS", "USER") == "hello from my model"
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["payload"]["model"] == "rootiq-network-v1" and seen["payload"]["messages"][0]["content"] == "SYS"
    assert ("authorization" in seen["headers"]) is expect_auth
