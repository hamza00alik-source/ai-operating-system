from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import connect
from ai_os.service import list_audit_events


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_task_and_approval_flow():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title": "Research demand", "department": "research"})
        assert task.status_code == 201
        approval = client.post("/approvals", json={
            "task_id": task.json()["id"], "action": "publish_content"
        })
        assert approval.status_code == 201
        aid = approval.json()["id"]
        decision = client.post(f"/approvals/{aid}/decision", json={"decision": "rejected"})
        assert decision.status_code == 200
        assert decision.json()["status"] == "rejected"


def test_approval_cannot_be_decided_twice():
    with TestClient(app) as client:
        approval = client.post("/approvals", json={"action": "spend_money"}).json()
        aid = approval["id"]
        assert client.post(
            f"/approvals/{aid}/decision", json={"decision": "approved"}
        ).status_code == 200
        assert client.post(
            f"/approvals/{aid}/decision", json={"decision": "rejected"}
        ).status_code == 409


def test_audit_trail_records_task_and_approval_lifecycle():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title": "Prepare campaign"}).json()
        approval = client.post("/approvals", json={
            "task_id": task["id"], "action": "publish_campaign"
        }).json()
        decided = client.post(
            f"/approvals/{approval['id']}/decision",
            json={"decision": "approved"},
        )
        assert decided.status_code == 200

    events = list_audit_events()
    relevant = [e for e in events if e["entity_id"] in {task["id"], approval["id"]}]
    assert {e["event_type"] for e in relevant} >= {
        "task.created", "approval.requested", "approval.approved"
    }


def test_audit_event_limit_is_bounded():
    assert len(list_audit_events(100000)) <= 500


def test_production_routes_require_api_key(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/tasks").status_code == 401
        assert client.get("/tasks", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/tasks", headers={"X-API-Key": "test-owner-key"}).status_code == 200


def test_non_development_requires_api_key_at_startup(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)
    try:
        with TestClient(app):
            raise AssertionError("Application startup should reject a missing API key")
    except RuntimeError as exc:
        assert "AI_OS_API_KEY" in str(exc)
