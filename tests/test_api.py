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
        assert client.get(f"/tasks/{task_id}/memory").json() == []
        assert client.get(f"/tasks/{task_id}/steps").json() == []
        assert client.get(f"/tasks/does-not-exist/memory").status_code == 404


def test_mcp_server_registry_lifecycle_without_secrets():
    with TestClient(app) as client:
        created = client.post("/mcp/servers", json={
            "name": "Example MCP", "endpoint": "https://mcp.example.com/v1",
            "credential_env": ["EXAMPLE_MCP_TOKEN"], "declared_capabilities": ["search", "read"],
        })
        assert created.status_code == 201
        server = created.json()
        assert server["connection_status"] == "not_connected"
        assert server["credential_env"] == ["EXAMPLE_MCP_TOKEN"]
        assert client.get("/mcp/servers").json()[0]["id"] == server["id"]
        toggled = client.post(f"/mcp/servers/{server['id']}/enabled?enabled=true")
        assert toggled.status_code == 200 and toggled.json()["enabled"] is True
        assert client.post("/mcp/servers/missing/enabled?enabled=false").status_code == 404


def test_mcp_registry_rejects_unsafe_endpoints_and_secret_values():
    with TestClient(app) as client:
        assert client.post("/mcp/servers", json={
            "name": "Local", "endpoint": "http://127.0.0.1:8000/mcp"
        }).status_code == 422
        assert client.post("/mcp/servers", json={
            "name": "Bad credential", "endpoint": "https://mcp.example.com",
            "credential_env": ["actual-secret-value"]
        }).status_code == 422


def test_mcp_registry_rejects_duplicate_endpoint():
    with TestClient(app) as client:
        body = {"name": "Duplicate", "endpoint": "https://duplicate.example.com/mcp"}
        assert client.post("/mcp/servers", json=body).status_code == 201
        assert client.post("/mcp/servers", json=body).status_code == 409


def test_audit_events_capture_task_and_approval_lifecycle():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title": "Audit me"}).json()
        approval = client.post("/approvals", json={
            "task_id": task["id"], "action": "publish", "actor_id": "owner",
            "resource_id": "store:demo", "action_payload": {"draft_id": "draft-1"}
        }).json()
        decision = client.post(f"/approvals/{approval['id']}/decision",
                               json={"decision": "approved"})
        assert decision.status_code == 200
        events = client.get("/audit/events").json()
        event_types = [event["event_type"] for event in events]
        assert "task.created" in event_types
        assert "approval.created" in event_types
        assert "approval.approved" in event_types
        assert client.get("/audit/events?limit=1").status_code == 200


def test_audit_pagination_uses_exclusive_cursor():
    with TestClient(app) as client:
        client.post("/tasks", json={"title": "First"})
        client.post("/tasks", json={"title": "Second"})
        first_page = client.get("/audit/events?limit=1").json()
        assert len(first_page) == 1
        second_page = client.get(f"/audit/events?limit=1&before_id={first_page[0]['id']}").json()
        assert len(second_page) == 1
        assert second_page[0]["id"] < first_page[0]["id"]


def test_audit_events_are_immutable_and_mcp_changes_are_recorded():
    import sqlite3
    from ai_os.db import connect

    with TestClient(app) as client:
        server = client.post("/mcp/servers", json={
            "name": "Audited MCP", "endpoint": "https://audit-mcp.example.com/mcp"
        }).json()
        client.post(f"/mcp/servers/{server['id']}/enabled?enabled=true")
        events = client.get("/audit/events").json()
        types = [event["event_type"] for event in events]
        assert "mcp_server.registered" in types
        assert "mcp_server.enabled" in types

        with connect() as db:
            event_id = db.execute("SELECT id FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()["id"]
            try:
                db.execute("UPDATE audit_events SET event_type='tampered' WHERE id=?", (event_id,))
            except sqlite3.IntegrityError as exc:
                assert "immutable" in str(exc)
            else:
                raise AssertionError("Audit update should be rejected")
            try:
                db.execute("DELETE FROM audit_events WHERE id=?", (event_id,))
            except sqlite3.IntegrityError as exc:
                assert "immutable" in str(exc)
            else:
                raise AssertionError("Audit deletion should be rejected")
