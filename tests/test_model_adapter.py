import json
from io import BytesIO

import pytest

from ai_os import model_adapter


def configure(monkeypatch, **overrides):
    values = {
        "AI_OS_MODEL_ENABLED": "true",
        "AI_OS_MODEL_PROVIDER": "test-provider",
        "AI_OS_MODEL_NAME": "test-model",
        "AI_OS_MODEL_BASE_URL": "https://models.example/v1",
        "AI_OS_MODEL_API_KEY": "secret-test-key",
        "AI_OS_MODEL_TIMEOUT_SECONDS": "10",
        "AI_OS_MODEL_MAX_TOKENS": "128",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_status_never_exposes_secret(monkeypatch):
    configure(monkeypatch)
    status = model_adapter.get_model_status()
    assert status["ready"] is True
    assert status["authentication"] == "configured"
    assert "secret-test-key" not in repr(status)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    assert model_adapter.get_model_status()["ready"] is False
    with pytest.raises(model_adapter.ModelAdapterError, match="disabled"):
        model_adapter.chat_completion("hello")


def test_chat_completion_uses_openai_compatible_request(monkeypatch):
    configure(monkeypatch)
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "model response"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }).encode()

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["payload"] = json.loads(request.data.decode())
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(model_adapter, "urlopen", fake_urlopen)
    result = model_adapter.chat_completion("hello")
    assert seen["url"] == "https://models.example/v1/chat/completions"
    assert seen["payload"]["model"] == "test-model"
    assert seen["payload"]["messages"][0]["content"] == "hello"
    assert seen["timeout"] == 10
    assert result["response"] == "model response"
    assert result["usage"]["completion_tokens"] == 2


def test_keyless_endpoint_does_not_send_auth_header(monkeypatch):
    configure(monkeypatch, AI_OS_MODEL_API_KEY="")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(request, timeout):
        captured.update(dict(request.header_items()))
        return FakeResponse()

    monkeypatch.setattr(model_adapter, "urlopen", fake_urlopen)
    model_adapter.chat_completion("hello")
    assert "Authorization" not in captured


def test_provider_http_error_is_sanitized(monkeypatch):
    from urllib.error import HTTPError

    configure(monkeypatch)

    def fail(*args, **kwargs):
        raise HTTPError("https://models.example", 429, "rate limit", {}, BytesIO(b"secret provider body"))

    monkeypatch.setattr(model_adapter, "urlopen", fail)
    with pytest.raises(model_adapter.ModelAdapterError, match="HTTP 429") as error:
        model_adapter.chat_completion("hello")
    assert "secret provider body" not in str(error.value)


def test_provider_catalogue_is_disabled_by_default():
    from ai_os.provider_catalog import list_providers

    providers = list_providers()
    assert providers
    assert all(item["default_enabled"] is False for item in providers)
    assert all("official_url" in item for item in providers)
