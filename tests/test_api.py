from fastapi.testclient import TestClient
from ai_os.api import app

def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_agent_registry_lists_enabled_agents():
    with TestClient(app) as client:
        response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) >= 8
    assert any(agent["id"] == "product-trend-researcher" for agent in agents)

def test_plan_routes_to_specialist_without_executing():
    with TestClient(app) as client:
        response = client.post("/plans", json={
            "title": "Research customer demand",
            "description": "Find evidence of willingness to pay.",
            "department": "research"
        })
    assert response.status_code == 201
    plan = response.json()
    assert plan["assigned_agent"]["id"] == "product-trend-researcher"
    assert plan["execution_enabled"] is False
    assert "No model" in plan["notice"]

def test_plan_rejects_unknown_department():
    with TestClient(app) as client:
        response = client.post("/plans", json={"title": "Unknown", "department": "not-a-team"})
    assert response.status_code == 404

def test_task_and_approval_flow():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title":"Research demand","department":"research"})
        assert task.status_code == 201
        approval = client.post("/approvals", json={
            "task_id": task.json()["id"], "action":"publish_content"
        })
        assert approval.status_code == 201
        aid = approval.json()["id"]
        decision = client.post(f"/approvals/{aid}/decision", json={"decision":"rejected"})
        assert decision.status_code == 200
        assert decision.json()["status"] == "rejected"

def test_approval_cannot_be_decided_twice():
    with TestClient(app) as client:
        approval = client.post("/approvals", json={"action":"spend_money"}).json()
        aid = approval["id"]
        assert client.post(f"/approvals/{aid}/decision", json={"decision":"approved"}).status_code == 200
        assert client.post(f"/approvals/{aid}/decision", json={"decision":"rejected"}).status_code == 409
