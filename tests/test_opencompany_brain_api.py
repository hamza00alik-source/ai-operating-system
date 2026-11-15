from fastapi.testclient import TestClient

from opencompany_app.api import app


def test_brain_plan_preview_is_owner_authenticated_and_never_executes(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "brain-test-owner-key")
    headers = {"X-API-Key": "brain-test-owner-key"}
    payload = {
        "business_id": "core",
        "max_parallel_agents": 2,
        "tasks": [
            {"task_id": "research-a", "role_key": "researcher_a",
             "department": "research", "objective": "Collect market evidence"},
            {"task_id": "research-b", "role_key": "researcher_b",
             "department": "research", "objective": "Collect competitor evidence"},
            {"task_id": "synthesis", "role_key": "analyst",
             "department": "research", "objective": "Synthesize both reports",
             "depends_on": ["research-a", "research-b"]},
        ],
    }
    with TestClient(app) as client:
        denied = client.post("/orchestration/brain/plan-preview", json=payload)
        assert denied.status_code == 401
        response = client.post(
            "/orchestration/brain/plan-preview", headers=headers, json=payload
        )
    assert response.status_code == 200
    result = response.json()
    assert result["batches"] == [["research-a", "research-b"], ["synthesis"]]
    assert result["execution_started"] is False
    assert result["queue_entries_created"] is False
    assert result["owner_approval_required"] is True
    assert all(task["review_required"] for task in result["tasks"])


def test_brain_plan_preview_rejects_cycles_and_unknown_business(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "brain-test-owner-key")
    headers = {"X-API-Key": "brain-test-owner-key"}
    cyclic = {
        "business_id": "core",
        "tasks": [
            {"task_id": "a", "role_key": "role_a", "department": "research",
             "objective": "A", "depends_on": ["b"]},
            {"task_id": "b", "role_key": "role_b", "department": "research",
             "objective": "B", "depends_on": ["a"]},
        ],
    }
    invalid_scope = {
        "business_id": "not-a-business",
        "tasks": [
            {"task_id": "a", "role_key": "role_a", "department": "research",
             "objective": "A"}
        ],
    }
    with TestClient(app) as client:
        cycle_response = client.post(
            "/orchestration/brain/plan-preview", headers=headers, json=cyclic
        )
        scope_response = client.post(
            "/orchestration/brain/plan-preview", headers=headers, json=invalid_scope
        )
    assert cycle_response.status_code == 422
    assert "cycle" in cycle_response.json()["detail"]
    assert scope_response.status_code == 422


def test_brain_status_reports_zero_cost_policy_without_credentials(monkeypatch):
    from types import SimpleNamespace
    from opencompany_app.api_dependencies import get_runtime

    class Gateway:
        def eligible_providers(self, *, request_budget_usd):
            assert request_budget_usd == 0.0
            return ("unorouter",)

    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "brain-test-owner-key")
    app.dependency_overrides[get_runtime] = lambda: SimpleNamespace(gateway=Gateway())
    try:
        with TestClient(app) as client:
            denied = client.get("/orchestration/brain/status")
            response = client.get(
                "/orchestration/brain/status",
                headers={"X-API-Key": "brain-test-owner-key"},
            )
        assert denied.status_code == 401
        assert response.status_code == 200
        result = response.json()
        assert result["eligible_zero_cost_providers"] == ["unorouter"]
        assert result["request_budget_usd"] == 0.0
        assert result["paid_fallback"] is False
        assert result["model_calls_performed"] is False
        assert "credentials" not in repr(result).lower()
    finally:
        app.dependency_overrides.pop(get_runtime, None)
