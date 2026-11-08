from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ai_os.llm import Provider
from ai_os.cascade import cascade_chat, AllProvidersFailed


@pytest.mark.asyncio
async def test_cascade_uses_first_successful_configured_provider(monkeypatch):
    providers = [
        Provider("first", "https://first.example/v1", "model-a", "FIRST_KEY", True),
        Provider("second", "https://second.example/v1", "model-b", "SECOND_KEY", True),
    ]
    monkeypatch.setenv("FIRST_KEY", "secret-a")
    monkeypatch.setenv("SECOND_KEY", "secret-b")
    with patch("ai_os.cascade.load_providers", return_value=providers), \
         patch("ai_os.cascade.httpx.AsyncClient") as client_cls:
        response = httpx.Response(200, json={"choices":[{"message":{"content":"ok"}}]})
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client_cls.return_value.__aenter__.return_value = client
        result = await cascade_chat("test")
    assert result["provider"] == "first"
    assert result["response"] == "ok"
    assert result["fallback_count"] == 0


@pytest.mark.asyncio
async def test_cascade_falls_back_after_provider_error(monkeypatch):
    providers = [
        Provider("first", "https://first.example/v1", "model-a", "FIRST_KEY", True),
        Provider("second", "https://second.example/v1", "model-b", "SECOND_KEY", True),
    ]
    monkeypatch.setenv("FIRST_KEY", "secret-a")
    monkeypatch.setenv("SECOND_KEY", "secret-b")
    with patch("ai_os.cascade.load_providers", return_value=providers), \
         patch("ai_os.cascade.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"choices":[{"message":{"content":"fallback worked"}}]}),
        ])
        client_cls.return_value.__aenter__.return_value = client
        result = await cascade_chat("test")
    assert result["provider"] == "second"
    assert result["fallback_count"] == 1


@pytest.mark.asyncio
async def test_cascade_does_not_use_unconfirmed_paid_provider(monkeypatch):
    monkeypatch.setenv("AI_OS_ALLOW_PAID_LLM", "false")
    monkeypatch.delenv("KEY", raising=False)
    providers = [Provider("paid", "https://paid.example/v1", "model", "KEY", False)]
    with patch("ai_os.cascade.load_providers", return_value=providers):
        with pytest.raises(LookupError):
            await cascade_chat("test")
