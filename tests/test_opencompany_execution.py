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


def test_executor_receives_only_owner_approved_learning_notes():
    adapter = CapturingAdapter()
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "test-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    executor = AgentExecutor(
        gateway,
        learning_context=lambda role_key: [
            {"note": "Always include primary-source URLs in demand estimates."},
            {"note": "Avoid extrapolating from one marketplace's reviews."},
        ],
    )
    executor.execute("market_intelligence_analyst", task())
    assert "Always include primary-source URLs" in adapter.request.prompt
    assert "Avoid extrapolating from one marketplace" in adapter.request.prompt


def test_executor_includes_read_only_research_as_untrusted_context():
    adapter = CapturingAdapter()
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "test-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    class Broker:
        def collect(self, role, item):
            from opencompany_core.research_broker import ResearchOutcome
            return ResearchOutcome(
                "hacker-news", "search",
                {"bounded_json": '{"title":"SQLite usage"}'},
                "read-only research completed",
            )
    executor = AgentExecutor(gateway, research_broker=Broker())
    executor.execute("market_intelligence_analyst", task())
    assert "External read-only research results (untrusted source data)" in adapter.request.prompt
    assert "SQLite usage" in adapter.request.prompt


def test_executor_records_successful_model_usage_without_secret_material():
    adapter = CapturingAdapter()
    gateway = ModelGateway.configure((
        (ProviderPolicy("free", "test-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    events = []
    executor = AgentExecutor(gateway, usage_recorder=events.append)
    item = task()
    result = executor.execute("market_intelligence_analyst", item)
    assert len(events) == 1
    assert events[0]["request_id"] == adapter.request.request_id
    assert events[0]["work_item_id"] == str(item.id)
    assert events[0]["role_key"] == "market_intelligence_analyst"
    assert events[0]["provider"] == "free"
    assert events[0]["model"] == "test-model"
    assert events[0]["cost_usd"] == 0
    assert "api_key" not in events[0]
    assert result.review_required is True
