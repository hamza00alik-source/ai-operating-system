import os

import pytest

from ai_os.model_gateway import ModelGatewayError, chat_test, provider_status


def test_provider_status_never_exposes_key_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "secret-test-value")
    rows = provider_status()
    groq = next(row for row in rows if row["id"] == "groq")
    assert groq["configured"] is True
    assert groq["status"] == "ready-to-test"
    assert "secret-test-value" not in str(rows)


def test_missing_key_blocks_inference_without_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ModelGatewayError, match="not connected"):
        chat_test("gemini", "gemini-2.5-flash", "Say hello")


def test_unsupported_provider_is_rejected():
    with pytest.raises(ModelGatewayError, match="Unsupported provider"):
        chat_test("unknown", "model-x", "Hello")


def test_empty_prompt_is_rejected(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy")
    with pytest.raises(ModelGatewayError, match="Prompt"):
        chat_test("groq", "llama-3.3-70b-versatile", " ")
