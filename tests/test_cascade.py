import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ai_os.llm import Provider
from ai_os.cascade import cascade_chat


def test_cascade_uses_first_successful_configured_provider(monkeypatch):
    providers = [Provider("first", "https://first.example/v1", "model-a", "FIRST_KEY", True)]
    monkeypatch.setenv("FIRST_KEY", "secret-a")
    with patch("ai_os.cascade.load_providers", return_value=providers), patch("ai_os.cascade.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.post = AsyncMock(return_value=httpx.Response(200, json={"choices":[{"message":{"content":"ok"}}]}))
        cls.return_value.__aenter__.return_value = client
        result = asyncio.run(cascade_chat("test"))
    assert result["provider"] == "first"
    assert result["response"] == "ok"


def test_cascade_falls_back_after_rate_limit(monkeypatch):
    providers = [
        Provider("first", "https://first.example/v1", "model-a", "FIRST_KEY", True),
        Provider("second", "https://second.example/v1", "model-b", "SECOND_KEY", True),
    ]
    monkeypatch.setenv("FIRST_KEY", "secret-a")
    monkeypatch.setenv("SECOND_KEY", "secret-b")
    with patch("ai_os.cascade.load_providers", return_value=providers), patch("ai_os.cascade.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"choices":[{"message":{"content":"fallback worked"}}]}),
        ])
        cls.return_value.__aenter__.return_value = client
        result = asyncio.run(cascade_chat("test"))
    assert result["provider"] == "second"
    assert result["fallback_count"] == 1


def test_cascade_blocks_unconfirmed_provider_without_owner_override(monkeypatch):
    monkeypatch.setenv("AI_OS_ALLOW_PAID_LLM", "false")
    monkeypatch.delenv("KEY", raising=False)
    providers = [Provider("paid", "https://paid.example/v1", "model", "KEY", False)]
    with patch("ai_os.cascade.load_providers", return_value=providers):
        with pytest.raises(LookupError):
            asyncio.run(cascade_chat("test"))


def test_cascade_supports_anonymous_provider_without_api_key(monkeypatch):
    monkeypatch.delenv("AI_OS_ALLOW_PAID_LLM", raising=False)
    provider = Provider(
        "ovhcloud-anonymous",
        "https://ovh.example/v1",
        "gpt-oss-20b",
        None,
        True,
        "none",
    )
    with patch("ai_os.cascade.load_providers", return_value=[provider]), patch("ai_os.cascade.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.post = AsyncMock(return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "anonymous works"}}]}
        ))
        cls.return_value.__aenter__.return_value = client
        result = asyncio.run(cascade_chat("test"))
    assert result["provider"] == "ovhcloud-anonymous"
    assert result["response"] == "anonymous works"
    headers = client.post.call_args.kwargs["headers"]
    assert "Authorization" not in headers
