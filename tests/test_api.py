from fastapi.testclient import TestClient
from ai_os.api import app

def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_runtime_explicitly_disables_paid_and_autonomous_execution():
    with TestClient(app) as client:
        response = client.get("/runtime")
    assert response.status_code == 200
    assert response.json()["paid_api_calls_enabled"] is False
    assert response.json()["autonomous_execution_enabled"] is False
    assert response.json()["external_actions_enabled"] is False

def test_agent_registry_lists_enabled_agents():
    with TestClient(app) as client:
        response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) >= 8
    assert any(agent["id"] == "product-trend-researcher" for agent in agents)

def test_plan_routes_to_specialist_without_executing():
    with TestClient(app) as client:
        response = client.post("/plans", json={"title": "Research customer demand", "description": "Find evidence of willingness to pay.", "department": "research"})
    assert response.status_code == 201
    plan = response.json()
    assert plan["assigned_agent"]["id"] == "product-trend-researcher"
    assert plan["execution_enabled"] is False
    assert "No model" in plan["notice"]

def test_plan_rejects_unknown_department():
    with TestClient(app) as client:
        response = client.post("/plans", json={"title": "Unknown", "department": "not-a-team"})
    assert response.status_code == 404

def test_work_packet_is_generated_without_api_call():
    with TestClient(app) as client:
        response = client.post("/work-packets", json={"agent_id": "product-trend-researcher", "task": "Research products customers are buying", "context": "Target international customers."})
    assert response.status_code == 201
    packet = response.json()
    assert packet["execution_mode"] == "manual_free_chat"
    assert packet["model_invoked"] is False
    assert packet["api_called"] is False
    assert "Research products customers are buying" in packet["prompt_text"]
    assert "Do not publish" in packet["prompt_text"]

def test_work_packet_rejects_unknown_agent():
    with TestClient(app) as client:
        response = client.post("/work-packets", json={"agent_id": "missing-agent", "task": "Do work"})
    assert response.status_code == 404

def test_work_packet_rejects_blank_task():
    with TestClient(app) as client:
        response = client.post("/work-packets", json={"agent_id": "product-trend-researcher", "task": "   "})
    assert response.status_code == 422

def test_task_and_approval_flow():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title":"Research demand","department":"research"})
        assert task.status_code == 201
        approval = client.post("/approvals", json={"task_id": task.json()["id"], "action":"publish_content"})
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

def test_job_queue_generates_packet_locally():
    with TestClient(app) as client:
        queued = client.post("/jobs", json={
            "job_type": "build_work_packet",
            "payload": {
                "agent_id": "product-trend-researcher",
                "task": "Research international buying demand",
                "context": "Find evidence of actual purchases."
            },
            "idempotency_key": "test-job-packet-001"
        })
        assert queued.status_code == 201
        assert queued.json()["status"] == "queued"
        result = client.post("/worker/run-once")
        assert result.status_code == 200
        assert result.json()["processed"] is True
        assert result.json()["job"]["status"] == "completed"
        assert result.json()["job"]["result"]["api_called"] is False
        assert "Research international buying demand" in result.json()["job"]["result"]["prompt_text"]

def test_job_idempotency_returns_existing_job():
    body = {
        "job_type": "build_work_packet",
        "payload": {"agent_id": "product-trend-researcher", "task": "Test idempotency"},
        "idempotency_key": "test-job-idempotency-001"
    }
    with TestClient(app) as client:
        first = client.post("/jobs", json=body)
        second = client.post("/jobs", json=body)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

def test_job_rejects_unknown_type():
    with TestClient(app) as client:
        response = client.post("/jobs", json={"job_type": "run_shell", "payload": {}})
    assert response.status_code == 422

def test_job_rejects_incomplete_payload():
    with TestClient(app) as client:
        response = client.post("/jobs", json={"job_type": "build_work_packet", "payload": {"task": "Missing agent"}})
    assert response.status_code == 422

def test_owner_token_is_required_when_configured(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_API_TOKEN", "test-owner-token-" + "x" * 40)
    with TestClient(app) as client:
        denied = client.get("/agents")
        allowed = client.get("/agents", headers={"Authorization": "Bearer " + "test-owner-token-" + "x" * 40})
    assert denied.status_code == 401
    assert allowed.status_code == 200

def test_production_fails_closed_without_owner_token(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.delenv("AI_OS_API_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/agents").status_code == 503

def test_audit_chain_records_requests_and_verifies():
    with TestClient(app) as client:
        assert client.get("/agents").status_code == 200
        verification = client.get("/audit/verify")
        events = client.get("/audit?limit=20")
    assert verification.status_code == 200
    assert verification.json()["valid"] is True
    assert verification.json()["checked_events"] >= 2
    assert events.status_code == 200
    assert any(event["resource_id"] == "/agents" for event in events.json()["events"])
