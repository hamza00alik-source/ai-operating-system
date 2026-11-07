from ai_os import department_management


def test_department_workload_uses_manager_source_division(monkeypatch):
    class Agent:
        def __init__(self, agent_id, name, department):
            self.id, self.name, self.department, self.enabled = agent_id, name, department, True

    manager = Agent("manager", "Manager", "growth-marketing")
    specialist = Agent("specialist", "Specialist", "growth-marketing")
    other = Agent("other", "Other", "engineering")

    monkeypatch.setattr(department_management, "get_department", lambda key: {
        "id": "marketing", "name": "Marketing", "mission": "Grow",
        "manager_agent_id": "manager",
    } if key == "marketing" else None)
    monkeypatch.setattr(department_management, "get_agent", lambda key: {
        "manager": manager, "specialist": specialist, "other": other,
    }.get(key))
    monkeypatch.setattr(department_management, "list_agents", lambda: [manager, specialist, other])
    monkeypatch.setattr(department_management, "list_company_runs", lambda limit=200: [{
        "id": "run-1", "title": "Growth", "steps": [
            {"step_key": "a", "agent_id": "specialist", "status": "completed",
             "depends_on": [], "updated_at": "2026-01-01", "report": {"summary": "Done"}},
            {"step_key": "b", "agent_id": "other", "status": "pending",
             "depends_on": [], "updated_at": "2026-01-02", "report": None},
        ],
    }])
    monkeypatch.setattr(department_management, "list_jobs", lambda limit=500: [])
    monkeypatch.setattr(department_management, "list_department_plans_for_runs", lambda run_ids: [])

    result = department_management.get_department_workload("marketing")
    assert result["manager"]["id"] == "manager"
    assert result["specialist_count"] == 2
    assert result["workload"] == {
        "total": 1, "pending": 0, "assigned": 0, "completed": 1, "blocked": 0,
    }
    assert result["items"][0]["agent_id"] == "specialist"
    assert result["execution_enabled"] is False


def test_unknown_department_has_no_workload(monkeypatch):
    monkeypatch.setattr(department_management, "get_department", lambda key: None)
    assert department_management.get_department_workload("missing") is None


def test_company_overview_reports_owner_governance(monkeypatch):
    monkeypatch.setattr(department_management, "list_departments", lambda: [
        {"id": "research"}, {"id": "marketing"},
    ])
    monkeypatch.setattr(department_management, "get_department_workload", lambda key, run_limit=200: {
        "id": key, "workload": {"total": 2, "pending": 1, "assigned": 0,
                                "completed": 1, "blocked": 0},
    })
    monkeypatch.setattr(department_management, "list_company_runs", lambda limit=200: [
        {"status": "queued"}, {"status": "completed"},
    ])
    result = department_management.get_company_overview()
    assert result["department_count"] == 2
    assert result["company_workload"]["total_department_assignments"] == 4
    assert result["company_runs"]["queued"] == 1
    assert result["governance"]["owner_approval_required_for_sensitive_actions"] is True
