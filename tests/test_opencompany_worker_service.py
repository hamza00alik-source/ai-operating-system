import json
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from opencompany_core.model_gateway import gateway_from_environment, ProviderUnavailable, UnoRouterFreeAdapter, ModelResult
from opencompany_app.worker_service import run_active_specialists_once
from opencompany_app.runtime import create_runtime


def test_gateway_fails_closed_without_free_confirmation(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "private-key")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "vendor/model:free")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "false")
    assert gateway_from_environment().eligible_providers(request_budget_usd=0.0) == ()


def test_gateway_rejects_non_free_model_even_with_confirmation(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "private-key")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "vendor/model")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "true")
    assert gateway_from_environment().eligible_providers(request_budget_usd=0.0) == ()


def test_gateway_configures_only_explicitly_confirmed_free_model(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "private-key")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "vendor/model:free")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "true")
    eligible = gateway_from_environment().eligible_providers(request_budget_usd=0.0)
    assert len(eligible) == 1
    assert eligible[0][0].name == "unorouter"
    assert eligible[0][0].max_cost_per_request_usd == 0.0


def test_adapter_never_sends_a_non_free_model():
    adapter = UnoRouterFreeAdapter("private-key")
    try:
        adapter.generate({"prompt": "hello"}, model="vendor/paid-model")
    except ProviderUnavailable as exc:
        assert "free" in str(exc)
    else:
        raise AssertionError("paid model was not rejected")


def test_adapter_uses_fixed_https_endpoint_and_records_zero_cost(monkeypatch):
    from opencompany_core import model_gateway
    captured = {}
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            assert limit == 1_000_000
            return json.dumps({
                "model": "vendor/model:free",
                "choices": [{"message": {"content": "A useful specialist draft with enough detail."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 18},
            }).encode()
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()
    monkeypatch.setattr(model_gateway.urllib.request, "urlopen", fake_urlopen)
    result = UnoRouterFreeAdapter("private-key").generate(
        {"prompt": "Prepare a research draft."}, model="vendor/model:free"
    )
    assert captured["url"] == "https://api.unorouter.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer private-key"
    assert captured["payload"]["model"] == "vendor/model:free"
    assert captured["timeout"] <= 60
    assert result.cost_usd == 0.0
    assert result.input_tokens == 12 and result.output_tokens == 18


def test_worker_iteration_ignores_inactive_specialists_and_processes_active_ones():
    active_id = str(uuid4())
    class FakeAgents:
        def values(self):
            return [
                {"id": active_id, "role_key": "researcher", "state": "active"},
                {"id": str(uuid4()), "role_key": "writer", "state": "paused"},
            ]
    class FakeWorker:
        def __init__(self): self.calls = []
        def run_once(self, agent_id, role_key):
            self.calls.append((str(agent_id), role_key))
            return "completed_review_required"
    class FakeQueue:
        def counts(self): return {"queued": 1}
    class FakeRuntime:
        def __init__(self):
            self.agents = FakeAgents()
            self.worker = FakeWorker()
            self.queue = FakeQueue()
    runtime = FakeRuntime()
    assert run_active_specialists_once(runtime) == 1
    assert runtime.worker.calls == [(active_id, "researcher")]


def test_worker_presence_survives_runtime_restart_and_records_stop(tmp_path):
    database = tmp_path / "worker-presence.sqlite3"
    first = create_runtime(str(database))
    worker_id = str(uuid4())
    first.worker_presence.start(worker_id)
    assert first.worker_presence.heartbeat(worker_id, 2) is True
    first.close()

    restarted = create_runtime(str(database))
    records = restarted.worker_presence.list_instances()
    assert len(records) == 1
    assert records[0]["worker_id"] == worker_id
    assert records[0]["state"] == "running"
    assert records[0]["processed_count"] == 2
    restarted.worker_presence.stop(worker_id)
    assert restarted.worker_presence.list_instances()[0]["state"] == "stopped"
    restarted.close()


def test_worker_presence_rejects_a_second_recent_worker_and_allows_stale_recovery(tmp_path):
    database = tmp_path / "single-worker.sqlite3"
    runtime = create_runtime(str(database))
    now = datetime.now(timezone.utc)
    runtime.worker_presence.start("worker-one", now)
    try:
        runtime.worker_presence.start("worker-two", now + timedelta(seconds=30))
    except RuntimeError as exc:
        assert "only one instance" in str(exc)
    else:
        raise AssertionError("a second active worker was allowed")
    runtime.worker_presence.start("worker-two", now + timedelta(seconds=121))
    assert len(runtime.worker_presence.list_instances()) == 2
    runtime.close()


def test_manager_executor_receives_only_scoped_memory_and_completed_team_deliverables():
    from opencompany_app.runtime import WorkItem
    from opencompany_core.domain import AuditRecord, TaskState
    from opencompany_core.execution import AgentDeliverable

    runtime = create_runtime(":memory:")
    manager_id = uuid4()
    role_key = "intelligence_research_manager"
    runtime.agents[role_key] = {
        "id": str(manager_id), "role_key": role_key, "title": "Research Manager",
        "kind": "leadership", "state": "active", "capabilities": ["synthesis"],
    }
    dependency = WorkItem(
        id=uuid4(), title="Specialist market scan", objective="Collect market evidence.",
        department="intelligence-research", state=TaskState.COMPLETED,
        business_id="digital-products",
    )
    runtime.store.create_work_item(dependency)
    audit = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="test.deliverable", subject_type="work_item",
        subject_id=str(dependency.id), outcome="recorded", correlation_id=str(uuid4()),
    )
    runtime.store.save_deliverable_with_audit(
        AgentDeliverable(
            id=uuid4(), work_item_id=dependency.id, role_key="market_researcher",
            content="Evidence: target buyers prefer downloadable offline tools.",
            provider="test", model="test", cost_usd=0.0,
        ),
        audit,
    )
    runtime.business.save_memory("digital-products", {
        "memory_key": "buyer-profile", "category": "strategy",
        "content": "Target customers are international PC gamers.",
        "source": "owner-approved research note",
    })
    runtime.business.save_memory("physical-agency", {
        "memory_key": "supplier-secret", "category": "supplier",
        "content": "This must not leak into digital products.",
        "source": "private supplier record",
    })

    parent = WorkItem(
        id=uuid4(), title="Synthesize market scan", objective="Prepare a management synthesis.",
        department="intelligence-research", state=TaskState.READY,
        business_id="digital-products", depends_on=(dependency.id,),
        assigned_agent_id=manager_id, assigned_role_key=role_key,
    )

    class FreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return (object(),)

        def generate(self, request, *, request_budget_usd=0.0):
            assert request_budget_usd == 0.0
            captured["prompt"] = request["prompt"]
            return ModelResult(
                text="Manager synthesis draft for owner review.",
                provider="test-free", model="test", cost_usd=0.0,
            )

    captured = {}
    runtime.gateway = FreeGateway()
    runtime.worker.executor.execute(role_key, parent)
    prompt = captured["prompt"]
    assert "Target customers are international PC gamers." in prompt
    assert "owner-approved research note" in prompt
    assert "Evidence: target buyers prefer downloadable offline tools." in prompt
    assert "synthesize the prerequisite specialist deliverables" in prompt.lower()
    assert "This must not leak into digital products." not in prompt
    runtime.close()


def test_worker_executor_refuses_uncompleted_or_cross_business_prerequisites():
    from opencompany_app.runtime import WorkItem
    from opencompany_core.domain import TaskState

    runtime = create_runtime(":memory:")
    manager_id = uuid4()
    role_key = "intelligence_research_manager"
    runtime.agents[role_key] = {
        "id": str(manager_id), "role_key": role_key, "title": "Research Manager",
        "kind": "leadership", "state": "active", "capabilities": ["synthesis"],
    }
    dependency = WorkItem(
        id=uuid4(), title="Incomplete prerequisite", objective="Still in progress.",
        department="intelligence-research", state=TaskState.READY,
        business_id="digital-products",
    )
    runtime.store.create_work_item(dependency)
    parent = WorkItem(
        id=uuid4(), title="Synthesis", objective="Combine team results.",
        department="intelligence-research", state=TaskState.READY,
        business_id="digital-products", depends_on=(dependency.id,),
        assigned_agent_id=manager_id, assigned_role_key=role_key,
    )
    with pytest.raises(ValueError, match="Every prerequisite must be completed"):
        runtime.worker.executor.execute(role_key, parent)
    runtime.close()
