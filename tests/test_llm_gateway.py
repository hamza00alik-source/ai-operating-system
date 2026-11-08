import json

import pytest
from fastapi.testclient import TestClient

from ai_os import llm_gateway
from ai_os.api import app


def clear_provider_env(monkeypatch):
    for name in (
        "AI_OS_GROQ_BASE_URL", "AI_OS_GROQ_MODEL", "AI_OS_GROQ_API_KEY",
        "AI_OS_GROQ_FREE_CONFIRMED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_provider_is_blocked_by_default(monkeypatch):
    clear_provider_env(monkeypatch)
    provider = next(p for p in llm_gateway.list_providers() if p["id"] == "groq")
    assert provider["configured"] is False
    assert provider["eligible"] is False


def test_provider_status_never_exposes_secret(monkeypatch):
    monkeypatch.setenv("AI_OS_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_OS_GROQ_MODEL", "example-model")
    monkeypatch.setenv("AI_OS_GROQ_API_KEY", "do-not-leak-this-secret")
    monkeypatch.setenv("AI_OS_GROQ_FREE_CONFIRMED", "true")
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "groq")
    assert status["eligible"] is True
    assert "do-not-leak-this-secret" not in json.dumps(status)
    assert "api_key" not in json.dumps(status).lower()


def test_gateway_executes_real_adapter_path_with_mocked_transport(monkeypatch):
    monkeypatch.setenv("AI_OS_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_OS_GROQ_MODEL", "example-model")
    monkeypatch.setenv("AI_OS_GROQ_API_KEY", "test-secret")
    monkeypatch.setenv("AI_OS_GROQ_FREE_CONFIRMED", "true")
    captured = {}

    def fake_post(url, payload, headers, timeout=35):
        captured.update(url=url, payload=payload, headers=headers)
        return {"choices": [{"message": {"content": "AIOS live connection successful"}}]}

    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.test_provider("groq")
    assert result["test_passed"] is True
    assert result["live"] is True
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"


def test_llm_endpoint_blocks_unconfigured_provider(monkeypatch):
    clear_provider_env(monkeypatch)
    with TestClient(app) as client:
        response = client.post("/llm/test", json={"provider": "groq", "prompt": "hello"})
    assert response.status_code == 403


def test_gemini_secret_is_sent_in_header_not_query_string(monkeypatch):
    monkeypatch.setenv("AI_OS_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
    monkeypatch.setenv("AI_OS_GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("AI_OS_GEMINI_API_KEY", "private-test-key")
    monkeypatch.setenv("AI_OS_GEMINI_FREE_CONFIRMED", "true")
    captured = {}

    def fake_post(url, payload, headers, timeout=35):
        captured.update(url=url, headers=headers)
        return {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}

    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.generate("gemini", "test")
    assert result["response"] == "hello"
    assert "private-test-key" not in captured["url"]
    assert "?" not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "private-test-key"


def test_provider_http_error_does_not_echo_response_body(monkeypatch):
    import io
    import urllib.error

    def fail_request(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://provider.invalid", 401, "Unauthorized", None,
            io.BytesIO(b"credential private-test-key"),
        )

    monkeypatch.setattr(llm_gateway.urllib.request, "urlopen", fail_request)
    with pytest.raises(RuntimeError) as exc:
        llm_gateway._post("https://provider.invalid", {}, {})
    assert "private-test-key" not in str(exc.value)
    assert "HTTP 401" in str(exc.value)
