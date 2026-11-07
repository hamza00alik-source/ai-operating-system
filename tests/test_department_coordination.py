import json

import pytest
from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import connect
from ai_os.execution import create_company_run
from ai_os.execution_schemas import CompanyRunCreate, RunStepCreate
from ai_os import department_coordination as coordination


class Agent:
    def __init__(self, agent_id, name, department):
        self.id = agent_id
        self.name = name
        self.department = department
        self.description = "Test specialist expertise."
        self.enabled = True


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'department-coordination.sqlite3'}")
    monkeypatch.setenv("AI_OS_API_TOKEN", "department-coordination-owner-" + "x" * 40)
    with TestClient(app):
        run = create_company_run(CompanyRunCreate(
            title="Prepare a product launch plan",
            description="Internal planning only.",
            steps=[RunStepCreate(
                step_key="seed",
                agent_id="product-trend-researcher",
                task="Identify market evidence.",
            )],
        ))
    manager = Agent("test-manager", "Test Department Manager", "research")
    specialist = Agent("product-trend-researcher", "Product Trend Researcher", "research")
    monkeypatch.setattr(coordination, "get_department", lambda key: {
        "id": "research", "name": "Research & R&D", "mission": "Find evidence",
        "manager_agent_id": "test-manager", "workstreams": ["market_research"],
        "approval_gates": ["external_message"],
    } if key == "research" else None)
    monkeypatch.setattr(coordination, "get_agent", lambda key: {
        "test-manager": manager, "product-trend-researcher": specialist,
    }.get(key))
    monkeypatch.setattr(coordination, "list_agents", lambda: [manager, specialist])
    monkeypatch.setattr(coordination, "load_agent_profile", lambda key: "Department manager profile.")
    return run["id"]


def test_manager_plan_persists_delegated_steps_and_is_idempotent(monkeypatch, tmp_path):
    run_id = _setup(monkeypatch, tmp_path)
    calls = []

    def fake_generate(system_prompt, user_prompt):
        calls.append((system_prompt, user_prompt))
        return ({"tasks": [{
            "step_key": "research_followup",
            "agent_id": "product-trend-researcher",
            "task": "Compare evidence for the target product.",
            "context": "Use source-backed findings.",
            "depends_on": [],
        }]}, {"provider": "test", "model": "mock-manager"})

    monkeypatch.setattr(coordination, "generate_json", fake_generate)
    result = coordination.create_department_plan(run_id, "research")
    assert result["status"] == "delegated"
    assert result["plan"]["manager_agent_id"] == "test-manager"
    assert result["plan"]["tasks"][0]["step_key"] == "research_followup"
    assert "Department manager profile." in calls[0][0]

    run = coordination.get_company_run(run_id) if hasattr(coordination, "get_company_run") else None
    assert run is None  # run retrieval belongs to the execution module
    from ai_os.execution import get_company_run
    updated = get_company_run(run_id)
    assert any(step["step_key"] == "research_followup" and step["status"] == "pending"
               for step in updated["steps"])

    again = coordination.create_department_plan(run_id, "research")
    assert again["reused_existing_plan"] is True
    assert len(calls) == 1
    assert len(coordination.list_department_plans(run_id)) == 1


def test_manager_cannot_delegate_outside_its_source_division(monkeypatch, tmp_path):
    run_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(coordination, "generate_json", lambda *_: ({
        "tasks": [{
            "step_key": "unsafe_assignment", "agent_id": "outside-agent",
            "task": "Do unrelated work.", "context": "", "depends_on": [],
        }]
    }, {"provider": "test", "model": "mock"}))
    with pytest.raises(ValueError, match="source division"):
        coordination.create_department_plan(run_id, "research")
    assert coordination.get_department_plan(run_id, "research") is None


def test_manager_review_waits_for_terminal_reports_then_records_ceo_summary(monkeypatch, tmp_path):
    run_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(coordination, "generate_json", lambda *_: ({
        "tasks": [{
            "step_key": "reviewable_task", "agent_id": "product-trend-researcher",
            "task": "Review customer demand.", "context": "", "depends_on": [],
        }]
    }, {"provider": "test", "model": "mock-manager"}))
    coordination.create_department_plan(run_id, "research")

    with pytest.raises(ValueError, match="only after every delegated task"):
        coordination.review_department_plan(run_id, "research")

    with connect() as db:
        db.execute(
            """UPDATE company_run_steps SET status='completed',report_json=?
               WHERE run_id=? AND step_key='reviewable_task'""",
            (json.dumps({
                "status": "completed", "summary": "Demand evidence reviewed.",
                "evidence": ["Evidence A"], "blockers": [],
            }), run_id),
        )

    def fake_review(system_prompt, user_prompt):
        assert "Department manager profile." in system_prompt
        return ({
            "status": "reviewed",
            "summary": "The delegated research is complete and useful.",
            "quality_findings": ["Evidence is traceable."],
            "blockers": [],
            "recommendations_for_ceo": ["Proceed to product definition."],
            "needs_ceo_attention": False,
        }, {"provider": "test", "model": "mock-manager"})

    monkeypatch.setattr(coordination, "generate_json", fake_review)
    result = coordination.review_department_plan(run_id, "research")
    assert result["status"] == "reviewed"
    assert result["review"]["reviewed_by"] == "test-manager"
    assert result["review"]["recommendations_for_ceo"] == ["Proceed to product definition."]
    repeated = coordination.review_department_plan(run_id, "research")
    assert repeated["reused_existing_review"] is True
