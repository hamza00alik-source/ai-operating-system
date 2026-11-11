import pytest

from opencompany_core.model_gateway import (
    BillingMode,
    CostPolicyViolation,
    ModelGateway,
    ModelRequest,
    ModelResult,
    ProviderPolicy,
)


class FreeAdapter:
    def generate(self, request, *, model):
        return ModelResult(
            text="A useful result",
            provider="unorouter",
            model=model,
            cost_usd=0.0,
            input_tokens=12,
            output_tokens=7,
        )


def gateway():
    return ModelGateway.configure((
        (ProviderPolicy("unorouter", "provider/free-model:free", BillingMode.FREE_CONFIRMED), FreeAdapter()),
    ))


def test_gateway_records_every_successful_model_call_with_request_identity():
    events = []
    model_gateway = gateway()
    model_gateway.set_usage_recorder(events.append)
    result = model_gateway.complete(
        ModelRequest(
            prompt="Summarize this evidence.",
            request_id="request-usage-001",
            work_item_id="work-item-001",
            role_key="market_demand_researcher",
        ),
        request_budget_usd=0.0,
    )
    assert result.cost_usd == 0.0
    assert events == [{
        "request_id": "request-usage-001",
        "work_item_id": "work-item-001",
        "role_key": "market_demand_researcher",
        "provider": "unorouter",
        "model": "provider/free-model:free",
        "input_tokens": 12,
        "output_tokens": 7,
        "cost_usd": 0.0,
    }]


def test_gateway_fails_closed_if_successful_inference_cannot_be_recorded():
    model_gateway = gateway()
    def fail_recording(event):
        raise OSError("simulated accounting storage failure")
    model_gateway.set_usage_recorder(fail_recording)
    with pytest.raises(CostPolicyViolation, match="durably recorded"):
        model_gateway.complete(
            ModelRequest(prompt="Do not lose accounting.", request_id="request-usage-002"),
            request_budget_usd=0.0,
        )


def test_gateway_records_reported_charge_before_rejecting_zero_cost_violation():
    events = []
    class ChargedAdapter:
        def generate(self, request, *, model):
            return ModelResult(
                text="The provider returned output but reported a charge.",
                provider="unorouter", model=model, cost_usd=0.01,
                input_tokens=9, output_tokens=4,
            )
    model_gateway = ModelGateway.configure((
        (ProviderPolicy("unorouter", "provider/free-model:free", BillingMode.FREE_CONFIRMED), ChargedAdapter()),
    ))
    model_gateway.set_usage_recorder(events.append)
    with pytest.raises(CostPolicyViolation, match="charge under a zero-cost policy"):
        model_gateway.complete(
            ModelRequest(
                prompt="Check reported billing.",
                request_id="request-usage-003",
                work_item_id="work-item-cost-check",
                role_key="finance_cost_auditor",
            ),
            request_budget_usd=0.0,
        )
    assert len(events) == 1
    assert events[0]["cost_usd"] == 0.01
    assert events[0]["role_key"] == "finance_cost_auditor"
