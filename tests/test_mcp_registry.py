import pytest
from fastapi.testclient import TestClient

from ai_os import api


def test_owner_can_register_enable_and_read_only_probe_mcp_server(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'mcp-registry.db'}")
    monkeypatch.setattr(api, "probe_mcp_server", lambda server_id: {
        "server_id": server_id, "connection_status": "connected",
        "tool_count": 1, "tools": [{"name": "search", "description": "Read-only search"}],
        "tool_execution_enabled": False, "execution_policy": "not_enabled",
    })

    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(api.app) as client:
        created = client.post("/integrations/mcp/servers", headers=headers, json={
            "name": "Research MCP",
            "endpoint": "https://mcp.example.com/mcp",
            "credential_env": ["AI_OS_RESEARCH_MCP_TOKEN"],
            "declared_capabilities": ["search"],
        })
        assert created.status_code == 201
        server = created.json()
        assert server["enabled"] is False
        assert server["credential_env"] == ["AI_OS_RESEARCH_MCP_TOKEN"]

        listed = client.get("/integrations/mcp/servers", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == server["id"]

        disabled_test = client.post(
            f"/integrations/mcp/servers/{server['id']}/test", headers=headers
        )
        assert disabled_test.status_code == 409

        enabled = client.post(
            f"/integrations/mcp/servers/{server['id']}/enabled",
            headers=headers, json={"enabled": True},
        )
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True

        tested = client.post(
            f"/integrations/mcp/servers/{server['id']}/test", headers=headers
        )
        assert tested.status_code == 200
        assert tested.json()["tool_execution_enabled"] is False

        duplicate = client.post("/integrations/mcp/servers", headers=headers, json={
            "name": "Duplicate", "endpoint": "https://mcp.example.com/mcp",
        })
        assert duplicate.status_code == 409


def test_mcp_registry_rejects_secret_values_as_credential_references(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'mcp-validation.db'}")
    with TestClient(api.app) as client:
        response = client.post("/integrations/mcp/servers", headers={
            "X-API-Key": "test-owner-key"
        }, json={
            "name": "Invalid server", "endpoint": "https://mcp.example.com/mcp",
            "credential_env": ["actual-secret-value"],
        })
    assert response.status_code == 422


def test_mcp_registry_requires_owner_authentication(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'mcp-auth.db'}")
    with TestClient(api.app) as client:
        assert client.get("/integrations/mcp/servers").status_code == 401
