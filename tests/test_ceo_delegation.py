import pytest

from ai_os import ceo_delegation


def test_ceo_delegates_only_to_manager_profiles_selected_in_run(monkeypatch):
    monkeypatch.setattr(ceo_delegation, "get_company_run", lambda run_id: {
        "id": run_id,
        "steps": [
            {"agent_id": "research-synthesist"},
            {"agent_id": "product-trend-researcher"},
            {"agent_id": "company-orchestrator"},
        ],
    })
    monkeypatch.setattr(ceo_delegation, "list_departments", lambda: [
        {"id": "research", "name": "Research", "manager_agent_id": "research-synthesist"},
        {"id": "marketing", "name": "Marketing", "manager_agent_id": "marketing-growth-hacker"},
    ])
    calls = []
    monkeypatch.setattr(ceo_delegation, "create_department_plan", lambda run_id, department_id: (
        calls.append((run_id, department_id)) or {
            "id": "plan-1", "status": "delegated", "plan": {"tasks": [{"step_key": "a"}]},
        }
    ))

    result = ceo_delegation.delegate_ceo_selected_departments("run-1")

    assert calls == [("run-1", "research")]
    assert result["selected_departments"] == ["research"]
    assert result["delegations"][0]["task_count"] == 1
    assert result["accountable_agent_id"] == "company-orchestrator"


def test_ceo_does_not_call_models_when_no_manager_was_selected(monkeypatch):
    monkeypatch.setattr(ceo_delegation, "get_company_run", lambda _: {
        "steps": [{"agent_id": "product-trend-researcher"}],
    })
    monkeypatch.setattr(ceo_delegation, "list_departments", lambda: [
        {"id": "research", "name": "Research", "manager_agent_id": "research-synthesist"},
    ])
    monkeypatch.setattr(
        ceo_delegation, "create_department_plan",
        lambda *_: pytest.fail("No manager model call should be made"),
    )

    result = ceo_delegation.delegate_ceo_selected_departments("run-2")

    assert result["selected_departments"] == []
    assert result["delegations"] == []


def test_ceo_delegation_rejects_unknown_run(monkeypatch):
    monkeypatch.setattr(ceo_delegation, "get_company_run", lambda _: None)
    with pytest.raises(LookupError, match="Company run not found"):
        ceo_delegation.delegate_ceo_selected_departments("missing")
