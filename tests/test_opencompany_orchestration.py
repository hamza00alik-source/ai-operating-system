import pytest
from fastapi.testclient import TestClient
from uuid import UUID, uuid4

from opencompany_app.api import app, get_runtime
from opencompany_app.catalogue import DEPARTMENT_CATALOGUE, ROLE_CATALOGUE
from opencompany_app.runtime import WorkItem, create_runtime, _audit
from opencompany_core.domain import TaskState
from opencompany_core.model_gateway import ModelResult


@pytest.fixture
def owner_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    runtime = create_runtime(str(tmp_path / "orchestration.sqlite3"))
    app.dependency_overrides[get_runtime] = lambda: runtime
    with TestClient(app, base_url="https://testserver") as client:
        yield client, runtime
    app.dependency_overrides.clear()
    runtime.close()


def _profile(role_key, state, kind):
    return {
        "id": str(uuid4()),
        "role_key": role_key,
        "name": role_key,
        "title": role_key,
        "department": "intelligence-research",
        "team_key": "intelligence-research__team_01",
        "capabilities": ["research"],
        "state": state,
        "revision": 1,
        "kind": kind,
    }


def test_ceo_orchestration_advances_only_assigned_active_dependency_ready_work(owner_client):
    client, runtime = owner_client
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}

    unauthenticated = client.get("/executive/orchestration/status")
    assert unauthenticated.status_code == 401

    runtime.agents["chief_executive_orchestrator"] = _profile(
        "chief_executive_orchestrator", "active", "leadership"
    )
    specialist = _profile("research_specialist", "active", "specialist")
    runtime.agents["research_specialist"] = specialist

    prerequisite = WorkItem(
        id=uuid4(), title="Gather sources", objective="Collect source material",
        department="intelligence-research", state=TaskState.COMPLETED,
    )
    eligible = WorkItem(
        id=uuid4(), title="Synthesize evidence", objective="Prepare an evidence brief",
        department="intelligence-research", state=TaskState.DRAFT,
        depends_on=(prerequisite.id,), assigned_agent_id=UUID(specialist["id"]),
        assigned_role_key="research_specialist",
    )
    blocked_dependency = WorkItem(
        id=uuid4(), title="Publish analysis draft", objective="Wait for upstream analysis",
        department="intelligence-research", state=TaskState.DRAFT,
        depends_on=(eligible.id,), assigned_agent_id=__import__("uuid").UUID(specialist["id"]),
        assigned_role_key="research_specialist",
    )
    unassigned = WorkItem(
        id=uuid4(), title="Unassigned research", objective="Needs an owner-approved assignment",
        department="intelligence-research", state=TaskState.DRAFT,
    )
    for item in (prerequisite, eligible, blocked_dependency, unassigned):
        runtime.store.create_work_item(item, _audit("test.created", item.id, "owner"))

    status = client.get("/executive/orchestration/status", headers=headers)
    assert status.status_code == 200
    snapshot = status.json()
    assert [x["work_item_id"] for x in snapshot["eligible_to_advance"]] == [str(eligible.id)]
    blocked = {x["work_item_id"]: x["reasons"] for x in snapshot["blocked_draft_items"]}
    assert "dependency_not_completed:" + str(eligible.id) in blocked[str(blocked_dependency.id)]
    assert "specialist_assignment_required" in blocked[str(unassigned.id)]

    advanced = client.post(
        "/executive/orchestration/advance", headers=headers, json={"max_items": 10}
    )
    assert advanced.status_code == 200
    result = advanced.json()
    assert result["advanced_count"] == 1
    assert result["items"][0]["id"] == str(eligible.id)
    assert result["items"][0]["state"] == "ready"
    assert result["items"][0]["revision"] == 2
    assert result["queue_admission_performed"] is False
    assert result["execution_started"] is False
    assert runtime.queue.counts() == {}

    repeated = client.post(
        "/executive/orchestration/advance", headers=headers, json={"max_items": 10}
    )
    assert repeated.status_code == 200
    assert repeated.json()["advanced_count"] == 0


def test_ceo_orchestration_requires_active_ceo_and_never_queues(owner_client):
    client, runtime = owner_client
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime.agents["chief_executive_orchestrator"] = _profile(
        "chief_executive_orchestrator", "draft", "leadership"
    )
    response = client.post(
        "/executive/orchestration/advance", headers=headers, json={}
    )
    assert response.status_code == 409
    assert runtime.queue.counts() == {}


def test_ceo_can_coordinate_active_managers_to_draft_delegations_without_assigning_or_queueing(owner_client):
    client, runtime = owner_client
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime.agents["chief_executive_orchestrator"] = _profile(
        "chief_executive_orchestrator", "active", "leadership"
    )
    department = next(
        value for value in DEPARTMENT_CATALOGUE
        if value["department"] == "intelligence-research"
    )
    manager_role = next(
        value for value in ROLE_CATALOGUE
        if value["role_key"] == department["manager_role_key"]
    )
    manager = {
        **_profile(manager_role["role_key"], "active", "leadership"),
        "title": manager_role["title"],
        "department": manager_role["department"],
    }
    runtime.agents[manager_role["role_key"]] = manager

    specialist_roles = [
        role for role in ROLE_CATALOGUE
        if role["department"] == "intelligence-research"
        and role["kind"] == "specialist"
        and role["team_key"] == "intelligence-research__team_01"
    ][:5]
    assert len(specialist_roles) == 5
    for role in specialist_roles:
        runtime.agents[role["role_key"]] = {
            **_profile(role["role_key"], "draft", "specialist"),
            "title": role["title"],
            "department": role["department"],
            "team_key": role["team_key"],
            "capabilities": role["capabilities"],
        }

    item = WorkItem(
        id=uuid4(), title="Research target market", objective="Prepare a sourced market opportunity brief",
        department="intelligence-research", state=TaskState.DRAFT,
        business_id="digital-products",
    )
    runtime.store.create_work_item(item, _audit("test.created", item.id, "owner"))

    class FreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return (object(),) if request_budget_usd == 0.0 else ()

        def generate(self, request, *, request_budget_usd=0.0):
            assert request_budget_usd == 0.0
            assert request["task"] == "propose_specialist_team"
            return ModelResult(
                text='{"required_capabilities":["market research"],"rationale":"A small specialist team can divide source discovery and synthesis."}',
                provider="test-free", model="test-model:free", cost_usd=0.0,
            )

    runtime.gateway = FreeGateway()
    response = client.post(
        "/executive/orchestration/draft-delegations",
        headers=headers,
        json={"business_id": "digital-products", "max_items": 3, "max_specialists": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["drafted_count"] == 1
    assert payload["owner_approval_required"] is True
    assert payload["assignment_performed"] is False
    assert payload["queue_entries_created"] is False
    assert payload["execution_started"] is False
    proposal = payload["drafted"][0]["proposal"]
    assert proposal["status"] == "draft"
    assert len(proposal["children"]) == 5
    assert runtime.store.get_work_item(item.id).assigned_agent_id is None
    assert runtime.queue.counts() == {}


def test_owner_can_reject_delegation_proposal_without_materializing_or_queueing(owner_client):
    client, runtime = owner_client
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    item = WorkItem(
        id=uuid4(), title="Prepare campaign analysis",
        objective="Assess the campaign opportunity",
        department="intelligence-research", state=TaskState.DRAFT,
        business_id="digital-products",
    )
    runtime.store.create_work_item(item, _audit("test.created", item.id, "owner"))
    proposal = {
        "id": str(uuid4()), "work_item_id": str(item.id),
        "department": item.department, "manager_role_key": "research_manager",
        "manager_agent_id": None, "status": "draft",
        "children": [{
            "id": str(uuid4()), "title": "Research source",
            "objective": item.objective, "department": item.department,
            "role_key": "research_specialist", "assigned_agent_id": str(uuid4()),
            "team_key": "intelligence-research__team_01", "state": "draft",
            "materialized_work_item_id": None,
        }],
        "queue_entries_created": False, "execution_started": False,
        "created_at": "2026-11-18T00:00:00+00:00",
        "updated_at": "2026-11-18T00:00:00+00:00",
    }
    runtime.delegations.save_proposal(proposal)

    response = client.post(
        f"/work-items/{item.id}/delegation-proposals/{proposal['id']}/reject",
        headers=headers, json={"rationale": "The proposed team is too broad."},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "rejected"
    assert result["owner_approval_required"] is False
    assert result["decision_rationale"] == "The proposed team is too broad."
    assert result["materialized_work_items"] == []
    assert result["queue_entries_created"] is False
    assert result["execution_started"] is False
    assert runtime.delegations.get_proposal(item.id, proposal["id"])["status"] == "rejected"
    assert len(runtime.store.list_work_items()) == 1
    assert runtime.queue.counts() == {}


def test_reject_delegation_proposal_requires_rationale_and_draft_state(owner_client):
    client, runtime = owner_client
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    item = WorkItem(
        id=uuid4(), title="Prepare campaign analysis",
        objective="Assess the campaign opportunity",
        department="intelligence-research", state=TaskState.DRAFT,
    )
    runtime.store.create_work_item(item, _audit("test.created", item.id, "owner"))
    proposal = {
        "id": str(uuid4()), "work_item_id": str(item.id),
        "status": "rejected", "children": [],
        "created_at": "2026-11-18T00:00:00+00:00",
        "updated_at": "2026-11-18T00:00:00+00:00",
    }
    runtime.delegations.save_proposal(proposal)
    url = f"/work-items/{item.id}/delegation-proposals/{proposal['id']}/reject"
    missing_rationale = client.post(url, headers=headers, json={"rationale": " "})
    assert missing_rationale.status_code == 422
    already_decided = client.post(url, headers=headers, json={"rationale": "No longer needed."})
    assert already_decided.status_code == 409
