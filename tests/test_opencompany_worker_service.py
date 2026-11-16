import json
from uuid import uuid4

from opencompany_core.model_gateway import gateway_from_environment, ProviderUnavailable, UnoRouterFreeAdapter
from opencompany_app.worker_service import run_active_specialists_once


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
    class FakeRuntime:
        def __init__(self):
            self.agents = FakeAgents()
            self.worker = FakeWorker()
    runtime = FakeRuntime()
    assert run_active_specialists_once(runtime) == 1
    assert runtime.worker.calls == [(active_id, "researcher")]
