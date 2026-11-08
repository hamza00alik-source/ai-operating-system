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


def test_owner_dashboard_is_served():
    with TestClient(app) as client:
        response = client.get("/owner")
    assert response.status_code == 200
    assert "Technology Discovery" in response.text
    assert "Queue scan" in response.text


def test_discovery_scan_queue_and_read_endpoints():
    with TestClient(app) as client:
        response = client.post("/discovery/scans", json={"categories": ["agent-frameworks"]})
        assert response.status_code == 202
        scan = response.json()
        assert scan["status"] == "queued"
        scans = client.get("/discovery/scans")
        assert scans.status_code == 200
        assert any(item["id"] == scan["id"] for item in scans.json())
        candidates = client.get("/discovery/candidates")
        assert candidates.status_code == 200


def test_discovery_scan_rejects_empty_categories():
    with TestClient(app) as client:
        response = client.post("/discovery/scans", json={"categories": []})
    assert response.status_code == 422


def test_research_analyst_endpoint_returns_persisted_run(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from ai_os.db import initialize_database
    from ai_os.api import app
    from ai_os.agent_runtime import run_research_analyst

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'api-agents.db'}")
    initialize_database()
    monkeypatch.setattr(
        "ai_os.api.run_research_analyst",
        lambda provider, goal: {
            "id": "test-run-id", "agent_type": "research_analyst",
            "goal": goal, "provider": provider, "status": "completed",
            "output": "Analysis saved.", "created_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    with TestClient(app) as client:
        response = client.post("/agents/runs", json={
            "provider": "groq",
            "goal": "Evaluate a small downloadable digital product idea.",
        })
        assert response.status_code == 201
        assert response.json()["status"] == "completed"
        assert response.json()["output"] == "Analysis saved."
        history = client.get("/agents/runs")
        assert history.status_code == 200
        assert history.json()[0]["id"] == "test-run-id"
