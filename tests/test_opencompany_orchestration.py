import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from opencompany_app.api import app, get_runtime
from opencompany_app.runtime import WorkItem, create_runtime, _audit
from opencompany_core.domain import TaskState


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
        depends_on=(prerequisite.id,), assigned_agent_id=__import__("uuid").UUID(specialist["id"]),
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
