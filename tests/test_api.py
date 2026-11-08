from fastapi.testclient import TestClient

from ai_os.api import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_owner_verification_dashboard_and_safe_runtime_status(monkeypatch):
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    monkeypatch.delenv("AI_OS_AGENT_GRAPH_ENABLED", raising=False)
    with TestClient(app) as client:
        page = client.get("/owner/verification")
        assert page.status_code == 200
        assert "Company control room" in page.text
        assert "Queue test task" in page.text
        status = client.get("/runtime/status")
        assert status.status_code == 200
        assert status.json()["model"]["enabled"] is False
        assert status.json()["agent_graph_enabled"] is False
        assert status.json()["worker_heartbeat_available"] is True
        assert status.json()["worker"]["status"] in {"never_seen", "active", "stale", "stopped"}
        assert "api_key" not in status.text.lower()


def test_task_and_approval_flow():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title": "Research demand", "department": "research"})
        assert task.status_code == 201
        assert task.json()["status"] == "queued"
        assert task.json()["result"] is None
        assert task.json()["error"] is None
        approval = client.post("/approvals", json={
            "task_id": task.json()["id"], "action": "publish_content",
            "actor_id": "spoofed-client-value", "resource_id": "wordpress:site-1",
            "action_payload": {"post_id": "draft-7", "visibility": "public"}
        })
        assert approval.status_code == 201
        assert approval.json()["actor_id"] == "local-development"
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
    monkeypatch.delenv("AI_OS_API_KEYS", raising=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/tasks").status_code == 401
        assert client.get("/tasks", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/tasks", headers={"X-API-Key": "test-owner-key"}).status_code == 200


def test_non_development_requires_api_key_at_startup(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)
    monkeypatch.delenv("AI_OS_API_KEYS", raising=False)
    try:
        with TestClient(app):
            raise AssertionError("Application startup should reject a missing API key")
    except RuntimeError as exc:
        assert "AI_OS_API_KEY" in str(exc) or "AI_OS_API_KEYS" in str(exc)


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


def test_distinct_principals_and_role_permissions(monkeypatch):
    import json
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)
    monkeypatch.setenv("AI_OS_API_KEYS", json.dumps({
        "owner-secret": {"principal_id": "owner-1", "role": "owner"},
        "viewer-secret": {"principal_id": "auditor-1", "role": "viewer"},
        "agent-secret": {"principal_id": "research-agent", "role": "agent"},
        "operator-secret": {"principal_id": "ops-1", "role": "operator"},
    }))
    with TestClient(app) as client:
        viewer = {"X-API-Key": "viewer-secret"}
        agent = {"X-API-Key": "agent-secret"}
        operator = {"X-API-Key": "operator-secret"}
        owner = {"X-API-Key": "owner-secret"}
        monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
        monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://provider.example/v1")
        monkeypatch.setenv("AI_OS_MODEL_NAME", "safe-test-model")
        from ai_os import api
        monkeypatch.setattr(api, "generate_text", lambda prompt, timeout: "AIOS_MODEL_CONNECTION_OK")
        assert client.post("/runtime/model-test", headers=viewer, json={}).status_code == 403
        assert client.post("/runtime/model-test", headers=owner, json={}).status_code == 200
        assert client.get("/tasks", headers=viewer).status_code == 200
        assert client.post("/tasks", headers=viewer, json={"title": "No"}).status_code == 403
        assert client.post("/tasks", headers=agent, json={"title": "Research"}).status_code == 201
        task = client.post("/tasks", headers=agent, json={"title": "Attributed"}).json()
        event = client.get("/audit/events", headers=viewer).json()[0]
        assert event["actor_id"] == "research-agent"
        approval = client.post("/approvals", headers=agent, json={
            "action": "publish", "actor_id": "spoofed", "resource_id": "site:1",
            "action_payload": {"draft": "x"}
        })
        assert approval.status_code == 403
        assert client.post("/mcp/servers", headers=viewer, json={
            "name": "blocked", "endpoint": "https://blocked.example.com/mcp"
        }).status_code == 403
        assert client.post("/approvals", headers=owner, json={
            "action": "publish", "actor_id": "spoofed", "resource_id": "site:1",
            "action_payload": {"draft": "x"}
        }).json()["actor_id"] == "owner-1"


def test_owner_model_connection_test_uses_fixed_prompt_without_real_network(monkeypatch):
    from ai_os import api

    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "free-test-model")
    calls = []
    monkeypatch.setattr(api, "generate_text", lambda prompt, timeout: calls.append((prompt, timeout)) or "AIOS_MODEL_CONNECTION_OK")

    with TestClient(app) as client:
        response = client.post("/runtime/model-test", json={})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model"] == "free-test-model"
    assert response.json()["output"] == "AIOS_MODEL_CONNECTION_OK"
    assert len(calls) == 1
    assert "private" not in calls[0][0].lower()
    assert calls[0][1] == 20


def test_owner_model_connection_test_refuses_when_disabled(monkeypatch):
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "free-test-model")
    with TestClient(app) as client:
        response = client.post("/runtime/model-test", json={})
    assert response.status_code == 409



def test_agent_mcp_tool_request_requires_owner_approval_before_execution(monkeypatch):
    from ai_os import api

    calls = []
    monkeypatch.setattr(
        api, "probe_and_call_mcp_tool",
        lambda server_id, tool_name, arguments: calls.append((server_id, tool_name, arguments))
        or {"server_id": server_id, "tool_name": tool_name, "result": {"content": [{"type": "text", "text": "ok"}]}},
    )
    with TestClient(app) as client:
        server = client.post("/mcp/servers", json={
            "name": "Request workflow MCP",
            "endpoint": "https://request-workflow.example.com/mcp",
        }).json()
        assert client.post(f"/mcp/servers/{server['id']}/enabled?enabled=true").status_code == 200

        requested = client.post("/mcp/tool-requests", json={
            "server_id": server["id"], "tool_name": "search",
            "arguments": {"query": "AIOS test"},
        })
        assert requested.status_code == 201
        request = requested.json()
        assert request["status"] == "pending"
        assert calls == []

        assert client.get("/mcp/tool-requests").json()[0]["id"] == request["id"]
        owner_review = client.post(f"/mcp/tool-requests/{request['id']}/approve")
        assert owner_review.status_code == 200
        approval = owner_review.json()["approval"]
        assert approval["status"] == "pending"
        assert owner_review.json()["request"]["status"] == "awaiting_approval"
        assert calls == []

        decision = client.post(
            f"/approvals/{approval['id']}/decision", json={"decision": "approved"}
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "approved"

        wrong_args = client.post(f"/mcp/servers/{server['id']}/tools/call", json={
            "tool_name": "search", "arguments": {"query": "tampered"},
            "approval_id": approval["id"], "request_id": request["id"],
        })
        assert wrong_args.status_code == 409
        assert calls == []

        executed = client.post(f"/mcp/servers/{server['id']}/tools/call", json={
            "tool_name": "search", "arguments": {"query": "AIOS test"},
            "approval_id": approval["id"], "request_id": request["id"],
        })
        assert executed.status_code == 200
        assert executed.json()["result"]["content"][0]["text"] == "ok"
        assert calls == [(server["id"], "search", {"query": "AIOS test"})]
        final_request = client.get("/mcp/tool-requests").json()[0]
        assert final_request["status"] == "executed"
        assert final_request["result"]["result"]["content"][0]["text"] == "ok"
        replay = client.post(f"/mcp/servers/{server['id']}/tools/call", json={
            "tool_name": "search", "arguments": {"query": "AIOS test"},
            "approval_id": approval["id"], "request_id": request["id"],
        })
        assert replay.status_code == 409
        assert len(calls) == 1
