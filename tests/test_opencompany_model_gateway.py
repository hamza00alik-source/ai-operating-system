import pytest

from opencompany_core.model_gateway import (
    BillingMode, CostPolicyViolation, ModelGateway, ModelRequest, ModelResult,
    NoEligibleProvider, ProviderPolicy, ProviderUnavailable,
)


class FakeAdapter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def generate(self, request, *, model):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def request():
    return ModelRequest("Prepare a sourced research brief.", "request-1")


def test_no_provider_is_enabled_by_default():
    gateway = ModelGateway()
    with pytest.raises(NoEligibleProvider):
        gateway.complete(request())


def test_unconfirmed_and_disabled_providers_are_never_selected():
    adapter = FakeAdapter(ModelResult("answer", "local", "model", 0))
    gateway = ModelGateway.configure((
        (ProviderPolicy("local", "model", BillingMode.DISABLED), adapter),
    ))
    with pytest.raises(NoEligibleProvider):
        gateway.complete(request())
    assert adapter.calls == 0


def test_confirmed_free_provider_can_be_selected_at_zero_budget():
    adapter = FakeAdapter(ModelResult("answer", "free", "small-model", 0))
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "small-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    result = gateway.complete(request())
    assert result.text == "answer"
    assert adapter.calls == 1


def test_paid_provider_remains_disabled_even_with_owner_approval_and_budget():
    adapter = FakeAdapter(ModelResult("answer", "paid", "large-model", 0.02))
    unapproved = ModelGateway.configure((
        (ProviderPolicy("paid", "large-model", BillingMode.DISABLED, 0.05), adapter),
    ))
    with pytest.raises(NoEligibleProvider):
        unapproved.complete(request(), request_budget_usd=1.0)
    approved = ModelGateway.configure((
        (ProviderPolicy("paid", "large-model", BillingMode.PAID_OWNER_APPROVED, 0.05), adapter),
    ))
    with pytest.raises(NoEligibleProvider):
        approved.complete(request(), request_budget_usd=0.01)
    assert adapter.calls == 0
    with pytest.raises(NoEligibleProvider):
        approved.complete(request(), request_budget_usd=0.05)
    assert adapter.calls == 0


def test_free_provider_charge_is_rejected():
    adapter = FakeAdapter(ModelResult("answer", "free", "model", 0.001))
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    with pytest.raises(CostPolicyViolation, match="zero-cost"):
        gateway.complete(request())


def test_fallback_only_uses_providers_that_pass_cost_policy():
    unavailable = FakeAdapter(error=ProviderUnavailable("quota exhausted"))
    free = FakeAdapter(ModelResult("answer", "backup", "model-b", 0))
    paid = FakeAdapter(ModelResult("paid answer", "paid", "model-p", 0.01))
    gateway = ModelGateway.configure((
        (ProviderPolicy("primary", "model-a", BillingMode.FREE_CONFIRMED, priority=1), unavailable),
        (ProviderPolicy("backup", "model-b", BillingMode.FREE_CONFIRMED, priority=2), free),
        (ProviderPolicy("paid", "model-p", BillingMode.PAID_OWNER_APPROVED, 0.02, priority=3), paid),
    ))
    result = gateway.complete(request())
    assert result.provider == "backup"
    assert paid.calls == 0


def test_provider_cannot_misidentify_its_response():
    adapter = FakeAdapter(ModelResult("answer", "other", "wrong-model", 0))
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    with pytest.raises(CostPolicyViolation, match="identity"):
        gateway.complete(request())


def test_duplicate_provider_names_are_rejected():
    adapter = FakeAdapter(ModelResult("answer", "free", "model", 0))
    policy = ProviderPolicy("free", "model", BillingMode.FREE_CONFIRMED)
    with pytest.raises(ValueError, match="unique"):
        ModelGateway.configure(((policy, adapter), (policy, adapter)))
