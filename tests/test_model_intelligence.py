from ai_os import model_intelligence


def test_provider_intelligence_reports_only_owner_confirmed_gateway_state(monkeypatch):
    monkeypatch.setattr(model_intelligence, "list_providers", lambda: [
        {"id": "free-a", "name": "Free A", "configured": True, "free_confirmed": True,
         "eligible": True, "experimental_only": False, "model": "model-a", "reason": None},
        {"id": "paid-b", "name": "Paid B", "configured": True, "free_confirmed": False,
         "eligible": False, "experimental_only": False, "model": "model-b", "reason": "Not confirmed"},
        {"id": "unset-c", "name": "Unset C", "configured": False, "free_confirmed": False,
         "eligible": False, "experimental_only": False, "model": None, "reason": "Not configured"},
    ])
    result = model_intelligence.provider_intelligence()
    assert result["summary"] == {
        "known_providers": 3,
        "configured_providers": 2,
        "free_confirmed_eligible": 1,
        "configured_but_blocked": 1,
    }
    assert result["mode"].startswith("configuration-only")
    assert "does not guarantee" in result["safety_note"]
    assert all("secret" not in str(provider).lower() for provider in result["providers"])


import pytest

from ai_os import model_benchmarks


def test_benchmark_ledger_persists_only_safe_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'benchmarks.db'}")
    from ai_os.db import initialize_database
    initialize_database()
    item = model_benchmarks.record_benchmark(
        provider="free-provider", model="model-x", outcome="passed",
        latency_ms=123, usage={"input_tokens": 10, "output_tokens": 20,
        "total_tokens": 30, "reported_by_provider": True},
        error=None, cost_class="owner-confirmed-free",
    )
    assert item["latency_ms"] == 123
    assert model_benchmarks.list_benchmarks()[0]["id"] == item["id"]
    assert model_benchmarks.list_benchmarks()[0]["total_tokens"] == 30
    assert "prompt" not in model_benchmarks.list_benchmarks()[0]


def test_benchmark_error_is_bounded_and_prompt_is_never_stored(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'benchmark-errors.db'}")
    from ai_os.db import initialize_database
    initialize_database()
    item = model_benchmarks.record_benchmark(
        provider="provider", model=None, outcome="error", latency_ms=None,
        usage=None, error="  " + ("failure " * 200), cost_class="owner-confirmed-free",
    )
    assert len(item["error_summary"]) <= 500
    assert item["input_tokens"] is None
    assert "prompt" not in item
