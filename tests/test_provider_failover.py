import pytest

from ai_os import llm_gateway


def _enable_openrouter(monkeypatch, model="provider/model:free", base="https://openrouter.ai/api/v1"):
    monkeypatch.setenv("AI_OS_OPENROUTER_BASE_URL", base)
    monkeypatch.setenv("AI_OS_OPENROUTER_MODEL", model)
    monkeypatch.setenv("AI_OS_OPENROUTER_API_KEY", "openrouter-test-key")
    monkeypatch.setenv("AI_OS_OPENROUTER_FREE_CONFIRMED", "true")


def test_rate_limited_free_route_fails_closed_without_paid_fallback(monkeypatch):
    _enable_openrouter(monkeypatch)
    calls = []

    def fake_generate(provider_id, prompt):
        calls.append(provider_id)
        raise llm_gateway.ProviderHTTPError(429, "rate limit reached")

    monkeypatch.setattr(llm_gateway, "generate", fake_generate)
    with pytest.raises(RuntimeError, match="No paid fallback was attempted"):
        llm_gateway.generate_with_fallback("test prompt", preferred_provider="openrouter")
    assert calls == ["openrouter"]


def test_fallback_never_uses_unconfirmed_or_unverified_provider(monkeypatch):
    for name in (
        "AI_OS_GEMINI_BASE_URL", "AI_OS_GEMINI_MODEL", "AI_OS_GEMINI_API_KEY",
        "AI_OS_GEMINI_FREE_CONFIRMED", "AI_OS_OPENROUTER_BASE_URL",
        "AI_OS_OPENROUTER_MODEL", "AI_OS_OPENROUTER_API_KEY",
        "AI_OS_OPENROUTER_FREE_CONFIRMED", "AI_OS_GROQ_BASE_URL",
        "AI_OS_GROQ_MODEL", "AI_OS_GROQ_API_KEY", "AI_OS_GROQ_FREE_CONFIRMED",
        "AI_OS_MISTRAL_BASE_URL", "AI_OS_MISTRAL_MODEL", "AI_OS_MISTRAL_API_KEY",
        "AI_OS_MISTRAL_FREE_CONFIRMED", "AI_OS_CLOUDFLARE_BASE_URL",
        "AI_OS_CLOUDFLARE_MODEL", "AI_OS_CLOUDFLARE_API_TOKEN",
        "AI_OS_CLOUDFLARE_FREE_CONFIRMED", "AI_OS_CUSTOM_BASE_URL",
        "AI_OS_CUSTOM_MODEL", "AI_OS_CUSTOM_API_KEY", "AI_OS_CUSTOM_FREE_CONFIRMED",
        "AI_OS_UNOROUTER_BASE_URL", "AI_OS_UNOROUTER_MODEL",
        "AI_OS_UNOROUTER_API_KEY", "AI_OS_UNOROUTER_FREE_CONFIRMED",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(PermissionError, match="No free-confirmed providers"):
        llm_gateway.generate_with_fallback("test prompt")


def test_bad_request_does_not_rotate_to_any_other_provider(monkeypatch):
    _enable_openrouter(monkeypatch)
    calls = []

    def fake_generate(provider_id, prompt):
        calls.append(provider_id)
        raise llm_gateway.ProviderHTTPError(400, "invalid request")

    monkeypatch.setattr(llm_gateway, "generate", fake_generate)
    with pytest.raises(llm_gateway.ProviderHTTPError):
        llm_gateway.generate_with_fallback("test prompt", preferred_provider="openrouter")
    assert calls == ["openrouter"]


def test_empty_or_placeholder_output_never_falls_back_to_unverified_provider(monkeypatch):
    _enable_openrouter(monkeypatch)
    calls = []

    def fake_generate(provider_id, prompt):
        calls.append(provider_id)
        raise RuntimeError("OpenRouter returned empty or placeholder text; refusing completion")

    monkeypatch.setattr(llm_gateway, "generate", fake_generate)
    with pytest.raises(RuntimeError, match="No paid fallback was attempted"):
        llm_gateway.generate_with_fallback("CEO review prompt", preferred_provider="openrouter")
    assert calls == ["openrouter"]


def test_unorouter_consumer_account_and_other_unverified_providers_are_skipped(monkeypatch):
    monkeypatch.setenv("AI_OS_UNOROUTER_BASE_URL", "https://api.unorouter.com/v1")
    monkeypatch.setenv("AI_OS_UNOROUTER_MODEL", "sample-model:free")
    monkeypatch.setenv("AI_OS_UNOROUTER_API_KEY", "unorouter-test-key")
    monkeypatch.setenv("AI_OS_UNOROUTER_FREE_CONFIRMED", "true")
    monkeypatch.setenv("AI_OS_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_OS_GROQ_MODEL", "free-model")
    monkeypatch.setenv("AI_OS_GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("AI_OS_GROQ_FREE_CONFIRMED", "true")
    calls = []

    monkeypatch.setattr(llm_gateway, "generate", lambda provider_id, prompt: calls.append(provider_id))
    with pytest.raises(PermissionError, match="No free-confirmed providers"):
        llm_gateway.generate_with_fallback("Prepare a company work draft")
    assert calls == []
    statuses = {item["id"]: item for item in llm_gateway.list_providers()}
    assert statuses["unorouter"]["eligible"] is False
    assert statuses["groq"]["eligible"] is False


def test_openrouter_model_must_use_official_endpoint_and_free_suffix(monkeypatch):
    _enable_openrouter(monkeypatch, model="provider/model")
    status = next(item for item in llm_gateway.list_providers() if item["id"] == "openrouter")
    assert status["eligible"] is False
    _enable_openrouter(monkeypatch, model="provider/model:free", base="https://example.invalid/v1")
    status = next(item for item in llm_gateway.list_providers() if item["id"] == "openrouter")
    assert status["eligible"] is False
