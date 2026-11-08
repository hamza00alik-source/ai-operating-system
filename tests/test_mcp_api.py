import pytest
from fastapi.testclient import TestClient

from ai_os.api import app


def test_owner_can_trigger_mcp_discovery_but_result_is_non_executable(monkeypatch):
    async def fake_discovery(endpoint_id):
        return {
            "endpoint_id": endpoint_id,
            "server_name": "Test MCP",
            "discovered_tool_count": 1,
            "tools": [{
                "name": "search", "description": "untrusted",
                "input_schema": {"type": "object"},
                "trust": "untrusted_remote_metadata",
                "executable": False,
                "owner_approval_required_before_mapping": True,
            }],
            "execution_enabled": False,
            "notice": "Discovery only.",
        }

    monkeypatch.setattr("ai_os.api.discover_mcp_tools", fake_discovery)
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/endpoints",
            json={"name": "MCP test", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp"},
        )
        endpoint_id = created.json()["endpoint_id"]
        client.patch(f"/control-plane/endpoints/{endpoint_id}", json={"enabled": True})
        response = client.post(f"/control-plane/endpoints/{endpoint_id}/discover")

    assert response.status_code == 200
    assert response.json()["discovered_tool_count"] == 1
    assert response.json()["tools"][0]["executable"] is False
    assert response.json()["execution_enabled"] is False


def test_mcp_discovery_failure_is_reported_without_tool_execution(monkeypatch):
    from ai_os.mcp_client import MCPDiscoveryError

    async def fail(_):
        raise MCPDiscoveryError("MCP host is not explicitly allowlisted.")

    monkeypatch.setattr("ai_os.api.discover_mcp_tools", fail)
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/endpoints",
            json={"name": "MCP test", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp"},
        )
        endpoint_id = created.json()["endpoint_id"]
        client.patch(f"/control-plane/endpoints/{endpoint_id}", json={"enabled": True})
        response = client.post(f"/control-plane/endpoints/{endpoint_id}/discover")

    assert response.status_code == 422
    assert "not explicitly allowlisted" in response.json()["detail"]
