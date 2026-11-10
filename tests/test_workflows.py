import pytest
from fastapi.testclient import TestClient
from ai_os import api


def test_workflow_starts_with_one_queued_step_and_gates_the_rest(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_API_KEY", "workflow-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'workflows.db'}")
    monkeypatch.setattr(api, "run_agent_pending_once", lambda: False)
    with TestClient(api.app) as client:
        catalog = client.get("/company/workflows")
        assert catalog.status_code == 200
        assert any(item["id"] == "digital-product-launch" for item in catalog.json()["templates"])
        created = client.post("/company/workflows/digital-product-launch/start", headers={"X-API-Key": "workflow-owner-key"})
        assert created.status_code == 201
        workflow = created.json()
        assert len(workflow["steps"]) == 7
        assert workflow["steps"][0]["status"] == "queued"
        assert all(step["status"] == "blocked" for step in workflow["steps"][1:])
        instances = client.get("/company/workflows/instances")
        assert instances.status_code == 200
        assert any(item["id"] == workflow["id"] for item in instances.json())
        blocked = client.post(f"/tasks/{workflow['steps'][1]['task_id']}/execute")
        assert blocked.status_code == 409
        queued = client.post(f"/tasks/{workflow['steps'][0]['task_id']}/execute")
        assert queued.status_code == 202


def test_workflow_handoff_unlocks_next_step_only_after_success(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'workflow-handoff.db'}")
    from ai_os.workflows import create_workflow, finish_workflow_task, get_workflow, task_is_runnable
    workflow = create_workflow("technology-evaluation")
    first, second = workflow["steps"][:2]
    assert task_is_runnable(first["task_id"]) is True
    assert task_is_runnable(second["task_id"]) is False
    finish_workflow_task(first["task_id"], True)
    current = get_workflow(workflow["id"])
    assert current["steps"][0]["status"] == "completed"
    assert current["steps"][1]["status"] == "queued"
    assert task_is_runnable(second["task_id"]) is True


def test_company_wide_cycle_is_business_scoped_and_covers_all_departments(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'company-cycle.db'}")
    from ai_os.workflows import create_workflow, list_workflows, task_is_runnable
    workflow = create_workflow("company-wide-operating-cycle", business_id="physical-agency")
    expected = [
        "executive", "research", "product", "design", "engineering", "legal-compliance",
        "quality-assurance", "marketing", "sales-marketplace", "customer-support",
        "finance", "people-workforce",
    ]
    assert [step["department"] for step in workflow["steps"]] == expected
    assert workflow["business_id"] == "physical-agency"
    assert len(workflow["steps"]) == 12
    assert workflow["steps"][0]["status"] == "queued"
    assert all(step["status"] == "blocked" for step in workflow["steps"][1:])
    assert task_is_runnable(workflow["steps"][0]["task_id"])
    assert not task_is_runnable(workflow["steps"][1]["task_id"])
    assert len(list_workflows(business_id="physical-agency")) == 1
    assert list_workflows(business_id="physical-brand") == []
    assert list_workflows(business_id="digital-products") == []
    with pytest.raises(ValueError):
        create_workflow("company-wide-operating-cycle", business_id="all-businesses")


def test_workflow_handoff_persists_output_for_next_department(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'workflow-output.db'}")
    from ai_os.db import connect
    from ai_os.workflows import create_workflow, finish_workflow_task, get_workflow
    workflow = create_workflow("company-wide-operating-cycle", business_id="physical-agency")
    first, second = workflow["steps"][:2]
    finish_workflow_task(first["task_id"], True, "Evidence: three verified buyer interviews.")
    with connect() as db:
        next_task = db.execute("SELECT description FROM tasks WHERE id=?", (second["task_id"],)).fetchone()
    assert "three verified buyer interviews" in next_task["description"]
    refreshed = get_workflow(workflow["id"])
    assert "three verified buyer interviews" in refreshed["steps"][0]["output"]
