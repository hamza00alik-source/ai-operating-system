"""Regression tests for OpenCompany's $0-only model routing policy."""
import pytest
from opencompany_core.model_gateway import (
    BillingMode, ModelGateway, ModelResult, ProviderPolicy, ProviderUnavailable,
)


class StubAdapter:
    def __init__(self, text="ok", cost=0.0):
        self.text = text
        self.cost = cost
        self.calls = 0

    def generate(self, request, *, model):
        self.calls += 1
        return ModelResult(self.text, "stub", model, self.cost)


def test_gateway_excludes_paid_and_unknown_providers():
    free = StubAdapter()
    paid = StubAdapter()
    unknown = StubAdapter()
    gateway = ModelGateway([
        (ProviderPolicy("free", "free-model", BillingMode.FREE_CONFIRMED, 0.0), free),
        (ProviderPolicy("paid", "paid-model", BillingMode.PAID, 0.0), paid),
        (ProviderPolicy("unknown", "unknown-model", BillingMode.UNKNOWN, 0.0), unknown),
    ])

    result = gateway.generate("hello", request_budget_usd=0.0)

    assert result.text == "ok"
    assert free.calls == 1
    assert paid.calls == 0
    assert unknown.calls == 0


def test_gateway_rejects_nonzero_request_budget_without_calling_provider():
    adapter = StubAdapter()
    gateway = ModelGateway([
        (ProviderPolicy("free", "free-model", BillingMode.FREE_CONFIRMED, 0.0), adapter),
    ])

    with pytest.raises(ProviderUnavailable, match="No paid fallback"):
        gateway.generate("hello", request_budget_usd=0.01)

    assert adapter.calls == 0


def test_gateway_rejects_provider_reported_nonzero_cost():
    adapter = StubAdapter(cost=0.001)
    gateway = ModelGateway([
        (ProviderPolicy("free", "free-model", BillingMode.FREE_CONFIRMED, 0.0), adapter),
    ])

    with pytest.raises(ProviderUnavailable, match="No paid fallback"):
        gateway.generate("hello", request_budget_usd=0.0)

    assert adapter.calls == 1


def test_gateway_does_not_fallback_when_free_provider_fails():
    failing = StubAdapter()
    paid = StubAdapter()
    failing.generate = lambda request, *, model: (_ for _ in ()).throw(RuntimeError("offline"))
    gateway = ModelGateway([
        (ProviderPolicy("free", "free-model", BillingMode.FREE_CONFIRMED, 0.0), failing),
        (ProviderPolicy("paid", "paid-model", BillingMode.PAID, 0.0), paid),
    ])

    with pytest.raises(ProviderUnavailable, match="No paid fallback"):
        gateway.generate("hello", request_budget_usd=0.0)

    assert paid.calls == 0
