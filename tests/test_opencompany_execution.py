import pytest
from uuid import uuid4

from opencompany_core.domain import TaskState, WorkItem
from opencompany_core.execution import AgentExecutor
from opencompany_core.model_gateway import (
    BillingMode, ModelGateway, ModelResult, NoEligibleProvider, ProviderPolicy,
)


class CapturingAdapter:
    def __init__(self):
        self.request = None

    def generate(self, request, *, model):
        self.request = request
        return ModelResult("Draft report with stated assumptions.", "free", model, 0)


def task(state=TaskState.IN_PROGRESS):
    return WorkItem(uuid4(), "Assess overseas demand",
                    "Prepare an evidence-based market assessment",
                    "research", state=state)


def test_executor_creates_reviewable_draft_from_original_role_spec():
    adapter = CapturingAdapter()
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "test-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    result = AgentExecutor(gateway).execute("market_intelligence_analyst", task())
    assert result.content.startswith("Draft report")
    assert result.review_required is True
    assert result.role_key == "market_intelligence_analyst"
    assert "Do not claim that research" in adapter.request.prompt
    assert "evidence-based market assessment" in adapter.request.prompt


def test_executor_rejects_tasks_not_in_progress():
    adapter = CapturingAdapter()
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "test-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    with pytest.raises(ValueError, match="in-progress"):
        AgentExecutor(gateway).execute(
            "market_intelligence_analyst", task(TaskState.READY)
        )
    assert adapter.request is None


def test_executor_cannot_call_a_disabled_provider():
    gateway = ModelGateway()
    with pytest.raises(NoEligibleProvider, match="No explicitly enabled provider"):
        AgentExecutor(gateway).execute("market_intelligence_analyst", task())


def test_unknown_role_is_rejected_before_model_call():
    adapter = CapturingAdapter()
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "test-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    with pytest.raises(LookupError, match="unknown OpenCompany role"):
        AgentExecutor(gateway).execute("not_a_role", task())
    assert adapter.request is None



def test_executor_automatically_uses_owner_configured_unorouter_free_provider(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "qwen/model:free")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "true")
    executor = AgentExecutor()
    assert executor._gateway.eligible_providers() == ("unorouter",)


def test_executor_default_gateway_stays_disabled_without_owner_configuration(monkeypatch):
    monkeypatch.delenv("OPENCOMPANY_UNOROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", raising=False)
    monkeypatch.delenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", raising=False)
    executor = AgentExecutor()
    assert executor._gateway.eligible_providers() == ()
