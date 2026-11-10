import io
import json
from urllib.error import HTTPError, URLError

import pytest

from opencompany_core.model_gateway import (
    BillingMode,
    ModelGateway,
    ModelRequest,
    NoEligibleProvider,
    ProviderUnavailable,
)
from opencompany_core import unorouter_adapter


def test_unorouter_is_available_to_company_gateway_when_owner_confirms_free_model(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "test-secret-key")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "qwen/qwen3-coder:free")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "true")

    configured = unorouter_adapter.configured_unorouter_provider()

    assert configured is not None
    policy, adapter = configured
    assert policy.name == "unorouter"
    assert policy.model == "qwen/qwen3-coder:free"
    assert policy.billing_mode == BillingMode.FREE_CONFIRMED
    gateway = ModelGateway.configure((configured,))
    assert gateway.eligible_providers() == ("unorouter",)
    assert adapter is not None


@pytest.mark.parametrize(
    "key,model,confirmation",
    [
        ("", "", ""),
        ("secret", "model:free", ""),
        ("secret", "model:paid", "true"),
        ("secret", "model:free", "false"),
    ],
)
def test_unorouter_partial_or_paid_configuration_fails_closed(monkeypatch, key, model, confirmation):
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", key)
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", model)
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", confirmation)
    assert unorouter_adapter.configured_unorouter_provider() is None


def test_unorouter_posts_chat_completion_and_returns_usage(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps({
                "model": "qwen/qwen3-coder:free",
                "choices": [{"message": {"content": "Draft completed."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "cost": 0},
            }).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(unorouter_adapter, "urlopen", fake_urlopen)
    adapter = unorouter_adapter.UnoRouterAdapter("secret")
    result = adapter.generate(
        ModelRequest("Write a short draft", "req-1", max_output_tokens=64),
        model="qwen/qwen3-coder:free",
    )

    assert captured["url"] == "https://api.unorouter.com/v1/chat/completions"
    assert captured["payload"]["model"] == "qwen/qwen3-coder:free"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["max_tokens"] == 64
    assert result.text == "Draft completed."
    assert result.provider == "unorouter"
    assert result.input_tokens == 12
    assert result.output_tokens == 8


def test_unorouter_gateway_rejects_provider_reported_cost(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps({
                "model": "model:free",
                "choices": [{"message": {"content": "Unexpectedly billed"}}],
                "usage": {"cost": 0.01},
            }).encode()

    monkeypatch.setattr(unorouter_adapter, "urlopen", lambda *a, **k: FakeResponse())
    configured = (
        unorouter_adapter.configured_unorouter_provider()
        if False else None
    )
    adapter = unorouter_adapter.UnoRouterAdapter("secret")
    from opencompany_core.model_gateway import ProviderPolicy, CostPolicyViolation
    gateway = ModelGateway.configure(((ProviderPolicy(
        name="unorouter", model="model:free",
        billing_mode=BillingMode.FREE_CONFIRMED, max_cost_per_request_usd=0,
    ), adapter),))
    with pytest.raises(CostPolicyViolation):
        gateway.complete(ModelRequest("test", "req-cost"), preferred_provider="unorouter")


def test_unorouter_transport_errors_are_safely_reported(monkeypatch):
    def fail(*args, **kwargs):
        raise URLError("secret diagnostic content")

    monkeypatch.setattr(unorouter_adapter, "urlopen", fail)
    adapter = unorouter_adapter.UnoRouterAdapter("secret")
    with pytest.raises(ProviderUnavailable, match="UnoRouter connection failed"):
        adapter.generate(ModelRequest("test", "req-fail"), model="model:free")


def test_unorouter_http_errors_do_not_leak_response_body(monkeypatch):
    def fail(*args, **kwargs):
        raise HTTPError("https://api.unorouter.com", 429, "rate limited", {}, io.BytesIO(b"private body"))

    monkeypatch.setattr(unorouter_adapter, "urlopen", fail)
    adapter = unorouter_adapter.UnoRouterAdapter("secret")
    with pytest.raises(ProviderUnavailable, match="HTTP 429") as exc:
        adapter.generate(ModelRequest("test", "req-429"), model="model:free")
    assert "private body" not in str(exc.value)


def test_unorouter_status_never_exposes_api_key(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "must-not-leak")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "model:free")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "true")
    status = unorouter_adapter.unorouter_configuration_status()
    assert status["configured"] is True
    assert status["model"] == "model:free"
    assert "must-not-leak" not in repr(status)
