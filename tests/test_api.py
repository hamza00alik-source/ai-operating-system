from fastapi.testclient import TestClient

from ai_os.api import app


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

def test_model_endpoints_are_safe_and_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)
    with TestClient(app) as client:
        status = client.get("/models/status")
        assert status.status_code == 200
        assert status.json()["ready"] is False
        assert "api_key" not in status.json()
        providers = client.get("/models/providers")
        assert providers.status_code == 200
        assert all(item["default_enabled"] is False for item in providers.json())
        response = client.post("/models/test", json={"prompt": "test"})
        assert response.status_code == 503
