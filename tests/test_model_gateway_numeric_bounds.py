import math

import pytest

from opencompany_core.model_gateway import (
    BillingMode,
    ModelGateway,
    ModelRequest,
    ModelResult,
    ProviderPolicy,
)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -0.01])
def test_provider_cost_ceiling_must_be_finite_and_non_negative(value):
    with pytest.raises(ValueError, match="finite"):
        ProviderPolicy("provider", "model", BillingMode.PAID_OWNER_APPROVED, value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -0.01])
def test_model_result_cost_must_be_finite_and_non_negative(value):
    with pytest.raises(ValueError, match="finite"):
        ModelResult("text", "provider", "model", value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -0.01])
def test_gateway_rejects_non_finite_or_negative_request_budget(value):
    gateway = ModelGateway()
    with pytest.raises(ValueError, match="finite"):
        gateway.eligible_providers(request_budget_usd=value)
    with pytest.raises(ValueError, match="finite"):
        gateway.complete(ModelRequest("prompt", "request"), request_budget_usd=value)
