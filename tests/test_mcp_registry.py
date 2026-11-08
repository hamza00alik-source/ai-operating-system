import json

import pytest

from ai_os.mcp_registry import MCPRegistryError, list_mcp_servers


def test_mcp_registry_empty_by_default(monkeypatch):
    monkeypatch.delenv("AI_OS_MCP_SERVERS_JSON", raising=False)
    assert list_mcp_servers() == []


def test_mcp_registry_redacts_credentials_and_requires_approval(monkeypatch):
    manifest = [{
        "id": "github",
        "name": "GitHub MCP",
        "transport": "streamable_http",
        "endpoint": "https://mcp.example.com/mcp",
        "enabled": True,
        "credential_env": "AI_OS_GITHUB_MCP_TOKEN",
        "allowed_tools": ["list_repositories"],
    }]
    monkeypatch.setenv("AI_OS_MCP_SERVERS_JSON", json.dumps(manifest))
    monkeypatch.setenv("AI_OS_GITHUB_MCP_TOKEN", "never-return-this-secret")
    result = list_mcp_servers()[0]
    assert result["connection_ready"] is True
    assert result["credential"] == "configured"
    assert result["approval_required"] is True
    assert result["execution_available"] is False
    assert "never-return-this-secret" not in repr(result)


def test_mcp_registry_rejects_http_and_unknown_transports(monkeypatch):
    manifest = [{
        "id": "unsafe",
        "name": "Unsafe MCP",
        "transport": "stdio",
        "endpoint": "http://127.0.0.1:8080",
    }]
    monkeypatch.setenv("AI_OS_MCP_SERVERS_JSON", json.dumps(manifest))
    with pytest.raises(MCPRegistryError):
        list_mcp_servers()


def test_mcp_registry_rejects_duplicate_ids(monkeypatch):
    item = {
        "id": "same",
        "name": "MCP",
        "transport": "streamable_http",
        "endpoint": "https://mcp.example.com",
    }
    monkeypatch.setenv("AI_OS_MCP_SERVERS_JSON", json.dumps([item, item]))
    with pytest.raises(MCPRegistryError, match="unique"):
        list_mcp_servers()
