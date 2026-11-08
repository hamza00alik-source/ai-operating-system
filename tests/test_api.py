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
            "task_id": task.json()["id"], "action": "publish_content",
            "actor_id": "owner", "resource_id": "wordpress:site-1",
            "action_payload": {"post_id": "draft-7", "visibility": "public"}
        })
        assert approval.status_code == 201
        aid = approval.json()["id"]
        decision = client.post(f"/approvals/{aid}/decision", json={"decision": "rejected"})
        assert decision.status_code == 200
        assert decision.json()["status"] == "rejected"


def test_approval_cannot_be_decided_twice():
    with TestClient(app) as client:
        approval = client.post("/approvals", json={"action": "spend_money", "actor_id": "owner", "resource_id": "wallet:main", "action_payload": {"amount": 5, "currency": "USD"}}).json()
        aid = approval["id"]
        assert client.post(f"/approvals/{aid}/decision", json={"decision": "approved"}).status_code == 200
        assert client.post(f"/approvals/{aid}/decision", json={"decision": "rejected"}).status_code == 409


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


def test_task_memory_and_step_status_endpoints():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title": "Test memory endpoints"})
        task_id = task.json()["id"]
        memory = client.get(f"/tasks/{task_id}/memory")
        steps = client.get(f"/tasks/{task_id}/steps")
        assert memory.status_code == 200
        assert memory.json() == []
        assert steps.status_code == 200
        assert steps.json() == []
        assert client.get("/tasks/does-not-exist/memory").status_code == 404


def test_mcp_server_registry_lifecycle_without_secrets():
    with TestClient(app) as client:
        created = client.post("/mcp/servers", json={
            "name": "Example MCP",
            "endpoint": "https://mcp.example.com/v1",
            "credential_env": ["EXAMPLE_MCP_TOKEN"],
            "declared_capabilities": ["search", "read"],
        })
        assert created.status_code == 201
        server = created.json()
        assert server["connection_status"] == "not_connected"
        assert server["credential_env"] == ["EXAMPLE_MCP_TOKEN"]
        assert "token" not in str(server).lower() or "EXAMPLE_MCP_TOKEN" in str(server)
        assert client.get("/mcp/servers").json()[0]["id"] == server["id"]
        toggled = client.post(f"/mcp/servers/{server['id']}/enabled?enabled=true")
        assert toggled.status_code == 200
        assert toggled.json()["enabled"] is True
        assert client.post(f"/mcp/servers/missing/enabled?enabled=false").status_code == 404


def test_mcp_registry_rejects_unsafe_endpoints_and_secret_values():
    with TestClient(app) as client:
        bad_url = client.post("/mcp/servers", json={
            "name": "Local", "endpoint": "http://127.0.0.1:8000/mcp"
        })
        assert bad_url.status_code == 422
        bad_secret = client.post("/mcp/servers", json={
            "name": "Bad credential", "endpoint": "https://mcp.example.com",
            "credential_env": ["actual-secret-value"]
        })
        assert bad_secret.status_code == 422


def test_mcp_registry_rejects_duplicate_endpoint():
    with TestClient(app) as client:
        body = {"name": "Duplicate", "endpoint": "https://duplicate.example.com/mcp"}
        assert client.post("/mcp/servers", json=body).status_code == 201
        assert client.post("/mcp/servers", json=body).status_code == 409
