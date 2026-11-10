import pytest

from ai_os import llm_gateway


def _enable(monkeypatch, prefix, base, model):
    monkeypatch.setenv(f"AI_OS_{prefix}_BASE_URL", base)
    monkeypatch.setenv(f"AI_OS_{prefix}_MODEL", model)
    monkeypatch.setenv(f"AI_OS_{prefix}_API_KEY", f"{prefix.lower()}-test-key")
    monkeypatch.setenv(f"AI_OS_{prefix}_FREE_CONFIRMED", "true")


def test_free_provider_failover_after_rate_limit(monkeypatch):
    _enable(monkeypatch, "GROQ", "https://api.groq.com/openai/v1", "free-model")
    _enable(monkeypatch, "GEMINI", "https://generativelanguage.googleapis.com", "gemini-flash")
    calls = []

    def fake_generate(provider_id, prompt):
        calls.append(provider_id)
        if provider_id == "groq":
            raise llm_gateway.ProviderHTTPError(429, "rate limit reached")
        return {
            "provider": provider_id,
            "model": "gemini-flash",
            "response": "A valid response from the backup provider.",
            "latency_ms": 12,
            "usage": {},
            "live": True,
        }

    monkeypatch.setattr(llm_gateway, "generate", fake_generate)
    result = llm_gateway.generate_with_fallback("test prompt", preferred_provider="groq")

    assert calls == ["groq", "gemini"]
    assert result["provider"] == "gemini"
    assert result["fallback_used"] is True
    assert result["provider_attempts"][0]["http_status"] == 429


def test_fallback_never_uses_unconfirmed_provider(monkeypatch):
    for name in (
        "AI_OS_GEMINI_BASE_URL", "AI_OS_GEMINI_MODEL", "AI_OS_GEMINI_API_KEY",
        "AI_OS_GEMINI_FREE_CONFIRMED", "AI_OS_GROQ_BASE_URL", "AI_OS_GROQ_MODEL",
        "AI_OS_GROQ_API_KEY", "AI_OS_GROQ_FREE_CONFIRMED",
        "AI_OS_MISTRAL_BASE_URL", "AI_OS_MISTRAL_MODEL", "AI_OS_MISTRAL_API_KEY",
        "AI_OS_MISTRAL_FREE_CONFIRMED", "AI_OS_CLOUDFLARE_BASE_URL",
        "AI_OS_CLOUDFLARE_MODEL", "AI_OS_CLOUDFLARE_API_TOKEN",
        "AI_OS_CLOUDFLARE_FREE_CONFIRMED", "AI_OS_CUSTOM_BASE_URL",
        "AI_OS_CUSTOM_MODEL", "AI_OS_CUSTOM_API_KEY", "AI_OS_CUSTOM_FREE_CONFIRMED",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(PermissionError, match="No free-confirmed providers"):
        llm_gateway.generate_with_fallback("test prompt")


def test_bad_request_does_not_rotate_providers(monkeypatch):
    _enable(monkeypatch, "GROQ", "https://api.groq.com/openai/v1", "free-model")
    _enable(monkeypatch, "GEMINI", "https://generativelanguage.googleapis.com", "gemini-flash")
    calls = []

    def fake_generate(provider_id, prompt):
        calls.append(provider_id)
        raise llm_gateway.ProviderHTTPError(400, "invalid request")

    monkeypatch.setattr(llm_gateway, "generate", fake_generate)
    with pytest.raises(llm_gateway.ProviderHTTPError):
        llm_gateway.generate_with_fallback("test prompt", preferred_provider="groq")
    assert calls == ["groq"]


def test_empty_or_placeholder_output_uses_free_fallback(monkeypatch):
    _enable(monkeypatch, "GROQ", "https://api.groq.com/openai/v1", "free-model")
    _enable(monkeypatch, "GEMINI", "https://generativelanguage.googleapis.com", "gemini-flash")
    calls = []

    def fake_generate(provider_id, prompt):
        calls.append(provider_id)
        if provider_id == "groq":
            raise RuntimeError("Groq returned empty or placeholder text; refusing to mark this agent stage complete")
        return {
            "provider": provider_id,
            "model": "gemini-flash",
            "response": "A valid CEO review from the backup free provider.",
            "latency_ms": 12,
            "usage": {},
            "live": True,
        }

    monkeypatch.setattr(llm_gateway, "generate", fake_generate)
    result = llm_gateway.generate_with_fallback("CEO review prompt", preferred_provider="groq")

    assert calls == ["groq", "gemini"]
    assert result["provider"] == "gemini"
    assert result["fallback_used"] is True
    assert result["provider_attempts"][0]["status"] == "invalid_or_empty_output"



def test_unorouter_consumer_account_is_skipped_for_company_task_failover(monkeypatch):
    _enable(monkeypatch, "UNOROUTER", "https://api.unorouter.com/v1", "sample-model:free")
    _enable(monkeypatch, "GROQ", "https://api.groq.com/openai/v1", "free-model")
    calls = []

    def fake_generate(provider_id, prompt):
        calls.append(provider_id)
        return {
            "provider": provider_id, "model": "free-model",
            "response": "A compliant provider returned a usable internal draft.",
            "latency_ms": 9, "usage": {}, "live": True,
        }

    monkeypatch.setattr(llm_gateway, "generate", fake_generate)
    result = llm_gateway.generate_with_fallback("Prepare a company work draft")
    assert calls == ["groq"]
    assert result["provider"] == "groq"
    uno = next(item for item in llm_gateway.list_providers() if item["id"] == "unorouter")
    assert uno["configured"] is True
    assert uno["eligible"] is False
