import json

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
        return {"choices": [{"message": {"content": "AIOS live connection successful"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}}

    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.test_provider("groq")
    assert result["test_passed"] is True
    assert result["live"] is True
    assert result["usage"]["total_tokens"] == 11
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"


def test_openrouter_free_route_uses_compatible_api_and_reports_usage(monkeypatch):
    monkeypatch.setenv("AI_OS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("AI_OS_OPENROUTER_MODEL", "provider/model:free")
    monkeypatch.setenv("AI_OS_OPENROUTER_API_KEY", "test-openrouter-secret")
    monkeypatch.setenv("AI_OS_OPENROUTER_FREE_CONFIRMED", "true")
    captured = {}

    def fake_post(url, payload, headers, timeout=35):
        captured.update(url=url, payload=payload, headers=headers)
        return {
            "choices": [{"message": {"content": "AIOS live connection successful"}}],
            "usage": {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        }

    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.test_provider("openrouter")
    assert result["test_passed"] is True
    assert result["provider"] == "openrouter"
    assert result["usage"]["total_tokens"] == 18
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-openrouter-secret"
    assert captured["headers"]["X-Title"] == "AI Operating System"
    assert captured["payload"]["model"] == "provider/model:free"


def test_openrouter_is_blocked_unless_owner_confirms_free(monkeypatch):
    monkeypatch.setenv("AI_OS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("AI_OS_OPENROUTER_MODEL", "provider/model:free")
    monkeypatch.setenv("AI_OS_OPENROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("AI_OS_OPENROUTER_FREE_CONFIRMED", "false")
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "openrouter")
    assert status["configured"] is True
    assert status["eligible"] is False


def test_llm_endpoint_blocks_unconfigured_provider(monkeypatch):
    clear_provider_env(monkeypatch)
    with TestClient(app) as client:
        response = client.post("/llm/test", json={"provider": "groq", "prompt": "hello"})
    assert response.status_code == 403



def test_fallback_error_identifies_each_provider_without_secrets(monkeypatch):
    def fake_config(provider):
        eligible = provider.key in {"openrouter", "groq"}
        return {"eligible": eligible, "configured": eligible, "free_confirmed": eligible}

    def fake_generate(provider_id, prompt):
        raise llm_gateway.ProviderHTTPError(403, "error code: 1010")

    monkeypatch.setattr(llm_gateway, "_provider_config", fake_config)
    monkeypatch.setattr(llm_gateway, "generate", fake_generate)

    try:
        llm_gateway.generate_with_fallback("test", preferred_provider="openrouter")
        assert False, "Expected all providers to fail"
    except RuntimeError as exc:
        message = str(exc)
        assert "openrouter: unavailable (HTTP 403)" in message
        assert "groq: unavailable (HTTP 403)" in message
        assert "No paid fallback was attempted" in message
        assert "secret" not in message.lower()


def test_unorouter_uses_openai_compatible_free_model_route(monkeypatch):
    monkeypatch.setenv("AI_OS_UNOROUTER_BASE_URL", "https://api.unorouter.com/v1")
    monkeypatch.setenv("AI_OS_UNOROUTER_MODEL", "example-model:free")
    monkeypatch.setenv("AI_OS_UNOROUTER_API_KEY", "unorouter-test-secret")
    monkeypatch.setenv("AI_OS_UNOROUTER_FREE_CONFIRMED", "true")
    captured = {}

    def fake_post(url, payload, headers, timeout=35):
        captured.update(url=url, payload=payload, headers=headers)
        return {"choices": [{"message": {"content": "AIOS live connection successful"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}

    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.test_provider("unorouter")
    assert result["test_passed"] is True
    assert captured["url"] == "https://api.unorouter.com/v1/chat/completions"
    assert captured["payload"]["model"] == "example-model:free"
    assert captured["headers"]["Authorization"] == "Bearer unorouter-test-secret"
    assert "unorouter-test-secret" not in json.dumps(llm_gateway.list_providers())


def test_unorouter_catalog_returns_only_online_free_models(monkeypatch):
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            return json.dumps({"counts":{"free":2},"models":[
                {"model_name":"alpha","is_free":True,"online":True,"type":"text"},
                {"model_name":"beta","is_free":True,"online":False,"type":"text"},
                {"model_name":"gamma","is_free":False,"online":True,"type":"text"}
            ]}).encode()
    monkeypatch.setattr(llm_gateway.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    data=llm_gateway.list_unorouter_free_models()
    assert data["available_online_free_count"] == 1
    assert data["models"][0]["id"] == "alpha:free"
