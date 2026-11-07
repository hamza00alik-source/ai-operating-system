import json
from io import BytesIO
from unittest.mock import patch

import pytest

from ai_os.llm import (
    LLMConfig,
    LLMConfigurationError,
    LLMRequestError,
    chat_completion,
)


def config(**overrides):
    values = {
        "enabled": True,
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "test-model",
        "api_key": "test-secret",
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return LLMConfig(**values)


def test_model_calls_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_OS_LLM_ENABLED", raising=False)
    with pytest.raises(LLMConfigurationError, match="disabled"):
        chat_completion([{"role": "user", "content": "hello"}])


def test_remote_http_endpoint_is_rejected():
    with pytest.raises(LLMConfigurationError, match="HTTPS"):
        chat_completion([{"role": "user", "content": "hello"}],
                        config=config(base_url="http://example.com/v1"))


def test_missing_provider_credentials_are_rejected():
    with pytest.raises(LLMConfigurationError, match="Configure"):
        chat_completion([{"role": "user", "content": "hello"}],
                        config=config(api_key=""))


def test_successful_completion_sends_expected_payload():
    body = {"choices": [{"message": {"content": "Hello from the test model"}}]}
    response = BytesIO(json.dumps(body).encode())
    with patch("urllib.request.urlopen", return_value=response) as mocked:
        result = chat_completion(
            [{"role": "user", "content": "hello"}],
            config=config(),
            max_tokens=100,
        )
    assert result == "Hello from the test model"
    request = mocked.call_args.args[0]
    sent = json.loads(request.data.decode())
    assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert sent["model"] == "test-model"
    assert sent["max_tokens"] == 100
    assert request.get_header("Authorization") == "Bearer test-secret"


def test_provider_http_error_is_sanitized():
    from urllib.error import HTTPError
    error = HTTPError("https://provider.invalid", 429, "limited", {}, BytesIO(b"private"))
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(LLMRequestError, match="HTTP 429") as raised:
            chat_completion([{"role": "user", "content": "hello"}], config=config())
    assert "private" not in str(raised.value)


def test_empty_or_invalid_messages_are_rejected():
    with pytest.raises(LLMConfigurationError, match="At least one"):
        chat_completion([], config=config())
    with pytest.raises(LLMConfigurationError, match="Messages"):
        chat_completion([{"role": "user", "content": 4}], config=config())


def test_invalid_max_tokens_are_rejected():
    with pytest.raises(LLMConfigurationError, match="max_tokens"):
        chat_completion([{"role": "user", "content": "hello"}],
                        config=config(), max_tokens=0)
