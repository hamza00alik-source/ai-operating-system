"""Restart-safe, owner-opted-in worker startup tests."""
from __future__ import annotations

from opencompany_app.runtime import create_runtime
from opencompany_core.model_gateway import ModelResult, ProviderUnavailable


class FakeGateway:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def eligible_providers(self, *, request_budget_usd=0.0):
        assert request_budget_usd == 0.0
        return ("unorouter",)

    def complete(self, request, *, request_budget_usd=0.0, preferred_provider=None):
        self.calls.append((request, request_budget_usd, preferred_provider))
        assert request_budget_usd == 0.0
        assert preferred_provider == "unorouter"
        if self.error:
            raise self.error
        return self.result


def _runtime(tmp_path, monkeypatch, gateway):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-test-key")
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "true")
    runtime = create_runtime(str(tmp_path / "autonomy.sqlite3"))
    runtime.gateway = gateway
    runtime.fleet.start = lambda: True
    return runtime


def test_restart_autostart_performs_fresh_zero_cost_provider_check(tmp_path, monkeypatch):
    gateway = FakeGateway(ModelResult(
        text="OPENCOMPANY_STARTUP_FREE_CHECK",
        provider="unorouter",
        model="example/free-model:free",
        cost_usd=0.0,
    ))
    runtime = _runtime(tmp_path, monkeypatch, gateway)
    try:
        assert runtime.unorouter_tested_at is None
        assert runtime.verify_free_provider_and_start() is True
        assert runtime.unorouter_tested_at is not None
        assert len(gateway.calls) == 1
        request, budget, preferred = gateway.calls[0]
        assert request.business_id == "core"
        assert request.role_key == "system"
        assert request.max_output_tokens == 24
        assert budget == 0.0
        assert preferred == "unorouter"
    finally:
        runtime.close()


def test_restart_autostart_stays_stopped_when_provider_reports_nonzero_cost(tmp_path, monkeypatch):
    gateway = FakeGateway(ModelResult(
        text="OPENCOMPANY_STARTUP_FREE_CHECK",
        provider="unorouter",
        model="example/free-model:free",
        cost_usd=0.001,
    ))
    runtime = _runtime(tmp_path, monkeypatch, gateway)
    started = []
    runtime.fleet.start = lambda: started.append(True) or True
    try:
        assert runtime.verify_free_provider_and_start() is False
        assert runtime.unorouter_tested_at is None
        assert started == []
    finally:
        runtime.close()


def test_restart_autostart_stays_stopped_on_unexpected_response(tmp_path, monkeypatch):
    gateway = FakeGateway(ModelResult(
        text="unexpected",
        provider="unorouter",
        model="example/free-model:free",
        cost_usd=0.0,
    ))
    runtime = _runtime(tmp_path, monkeypatch, gateway)
    started = []
    runtime.fleet.start = lambda: started.append(True) or True
    try:
        assert runtime.verify_free_provider_and_start() is False
        assert runtime.unorouter_tested_at is None
        assert started == []
    finally:
        runtime.close()


def test_restart_autostart_stays_stopped_when_provider_is_unavailable(tmp_path, monkeypatch):
    gateway = FakeGateway(error=ProviderUnavailable("temporarily unavailable"))
    runtime = _runtime(tmp_path, monkeypatch, gateway)
    started = []
    runtime.fleet.start = lambda: started.append(True) or True
    try:
        assert runtime.verify_free_provider_and_start() is False
        assert runtime.unorouter_tested_at is None
        assert started == []
    finally:
        runtime.close()


def test_restart_autostart_does_not_probe_without_owner_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-test-key")
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "false")
    gateway = FakeGateway(ModelResult(
        text="OPENCOMPANY_STARTUP_FREE_CHECK",
        provider="unorouter",
        model="example/free-model:free",
        cost_usd=0.0,
    ))
    runtime = create_runtime(str(tmp_path / "autonomy-disabled.sqlite3"))
    runtime.gateway = gateway
    started = []
    runtime.fleet.start = lambda: started.append(True) or True
    try:
        assert runtime.verify_free_provider_and_start() is False
        assert gateway.calls == []
        assert started == []
    finally:
        runtime.close()
