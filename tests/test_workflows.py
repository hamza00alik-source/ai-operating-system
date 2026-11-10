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
    from ai_os.db import connect
    with connect() as db:
        next_run = db.execute("SELECT status FROM agent_runs WHERE task_id=?", (second["task_id"],)).fetchone()
    assert next_run["status"] == "queued"


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
    from ai_os.db import connect
    with connect() as db:
        first_run = db.execute("SELECT status FROM agent_runs WHERE task_id=?",
                               (workflow["steps"][0]["task_id"],)).fetchone()
    assert first_run["status"] == "queued"
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


def test_full_company_cycle_completes_with_isolated_handoffs_for_each_business(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'all-business-cycles.db'}")
    from ai_os.workflows import create_workflow, finish_workflow_task, get_workflow

    business_ids = ("physical-agency", "physical-brand", "digital-products")
    completed_workflows = []
    for business_id in business_ids:
        workflow = create_workflow("company-wide-operating-cycle", business_id=business_id)
        for index, step in enumerate(workflow["steps"]):
            deliverable = f"{business_id} department {index + 1} verified deliverable"
            finish_workflow_task(step["task_id"], True, deliverable)
            refreshed = get_workflow(workflow["id"])
            assert refreshed["steps"][index]["status"] == "completed"
            assert refreshed["steps"][index]["output"] == deliverable
            if index + 1 < len(workflow["steps"]):
                from ai_os.db import connect
                with connect() as db:
                    following = db.execute("SELECT description, business_id FROM tasks WHERE id=?",
                                           (workflow["steps"][index + 1]["task_id"],)).fetchone()
                assert deliverable in following["description"]
                assert following["business_id"] == business_id
        final = get_workflow(workflow["id"])
        assert final["status"] == "completed"
        assert all(step["status"] == "completed" for step in final["steps"])
        assert final["business_id"] == business_id
        completed_workflows.append(final["id"])

    assert len(set(completed_workflows)) == 3


def test_workflow_handoff_creates_business_scoped_department_message(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'handoff-message.db'}")
    from ai_os.department_collaboration import list_messages
    from ai_os.workflows import create_workflow, finish_workflow_task
    workflow=create_workflow("company-wide-operating-cycle",business_id="physical-brand")
    first,second=workflow["steps"][:2]
    finish_workflow_task(first["task_id"],True,"Research output: verified demand signals.")
    inbox=list_messages("physical-brand",department="research")
    assert len(inbox)==1
    assert inbox[0]["sender_department"]=="executive"
    assert inbox[0]["recipient_department"]=="research"
    assert inbox[0]["related_task_id"]==second["task_id"]
    assert "verified demand signals" in inbox[0]["body"]
    assert list_messages("physical-agency",department="research")==[]


def test_departments_can_message_and_delegate_only_within_business(monkeypatch,tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL",f"sqlite:///{tmp_path / 'department-collaboration.db'}")
    from ai_os.department_collaboration import delegate_task,list_delegations,list_messages,mark_message_read,send_message
    from ai_os.service import create_task
    from ai_os.schemas import TaskCreate
    from ai_os.db import initialize_database
    initialize_database()
    parent=create_task(TaskCreate(title="Prepare research brief",description="Scope task",
                                  department="research",business_id="digital-products"))
    message=send_message("digital-products","research","product","Research findings",
                         "Please turn the evidence into product requirements.",parent["id"])
    assert message["status"]=="unread"
    assert list_messages("physical-brand",department="product")==[]
    assert mark_message_read(message["id"],"digital-products","product")["status"]=="read"
    delegated=delegate_task("digital-products","research","product","Draft product requirements",
                            "Use only verified findings.",parent["id"])
    assert delegated["status"]=="queued"
    assert delegated["run_status"]=="queued"
    from ai_os.db import connect
    with connect() as db:
        delegated_run=db.execute("SELECT status FROM agent_runs WHERE task_id=?",
                                 (delegated["child_task_id"],)).fetchone()
    assert delegated_run["status"]=="queued"
    assert delegated["from_department"]=="research" and delegated["to_department"]=="product"
    assert len(list_delegations("digital-products",department="product"))==1
    assert list_messages("digital-products",department="product")[0]["related_task_id"]==delegated["child_task_id"]
    with pytest.raises(LookupError):
        send_message("digital-products","research","product","Cross-scope","No leak.","not-a-task")
    with pytest.raises(LookupError):
        delegate_task("digital-products","research","finance","Wrong parent","No.",parent_task_id="not-a-task")


def test_collaboration_api_requires_owner_for_writes_and_validates_departments(monkeypatch,tmp_path):
    monkeypatch.setenv("AI_OS_ENV","development")
    monkeypatch.setenv("AI_OS_API_KEY","collab-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL",f"sqlite:///{tmp_path / 'collaboration-api.db'}")
    with TestClient(api.app) as client:
        payload={"business_id":"physical-agency","sender_department":"research",
                 "recipient_department":"product","subject":"Evidence handoff","body":"Verified source notes."}
        assert client.post("/company/collaboration/messages",json=payload).status_code==401
        created=client.post("/company/collaboration/messages",json=payload,headers={"X-API-Key":"collab-owner-key"})
        assert created.status_code==201 and created.json()["business_id"]=="physical-agency"
        bad={**payload,"sender_department":"unknown"}
        assert client.post("/company/collaboration/messages",json=bad,
                           headers={"X-API-Key":"collab-owner-key"}).status_code==422
        inbox=client.get("/company/collaboration/messages?business_id=physical-agency&department=product",
                         headers={"X-API-Key":"collab-owner-key"})
        assert inbox.status_code==200 and len(inbox.json())==1
