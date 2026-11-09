from contextlib import contextmanager

import pytest

from ai_os import mcp_client


class FakeDB:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args):
        return self

    def fetchone(self):
        return self.row


def install_server(monkeypatch):
    row = {
        "id": "server-1", "name": "Example MCP",
        "endpoint": "https://mcp.example.com/mcp", "enabled": 1,
        "credential_env_json": "[]",
    }

    @contextmanager
    def fake_connect():
        yield FakeDB(row)

    monkeypatch.setattr(mcp_client, "connect", fake_connect)
    monkeypatch.setattr(mcp_client, "_public_endpoint", lambda _endpoint: None)
    monkeypatch.setattr(mcp_client, "_open_session", lambda *_args: ({"MCP-Protocol-Version": "2025-03-26"}, "2025-03-26", {}))
    monkeypatch.setattr(mcp_client, "_list_tools", lambda *_args: [{
        "name": "lookup", "inputSchema": {
            "type": "object", "required": ["query"],
            "properties": {"query": {"type": "string"}},
            "additionalProperties": False,
        }
    }])


def test_mcp_tool_call_rejects_unknown_tool(monkeypatch):
    install_server(monkeypatch)
    monkeypatch.setattr(mcp_client, "_list_tools", lambda *_args: [])
    with pytest.raises(LookupError, match="not currently advertised"):
        mcp_client.call_mcp_tool("server-1", "missing", {})


def test_mcp_tool_call_validates_required_arguments_before_network_call(monkeypatch):
    install_server(monkeypatch)
    monkeypatch.setattr(mcp_client, "_post", lambda *_args: pytest.fail("tool must not be invoked"))
    with pytest.raises(ValueError, match="failed schema validation"):
        mcp_client.call_mcp_tool("server-1", "lookup", {})


def test_mcp_tool_call_rejects_unexpected_arguments(monkeypatch):
    install_server(monkeypatch)
    monkeypatch.setattr(mcp_client, "_post", lambda *_args: pytest.fail("tool must not be invoked"))
    with pytest.raises(ValueError, match="failed schema validation"):
        mcp_client.call_mcp_tool("server-1", "lookup", {"query": "x", "admin": True})


def test_mcp_tool_call_invokes_only_advertised_tool(monkeypatch):
    install_server(monkeypatch)
    calls = []

    def fake_post(_opener, _endpoint, payload, _headers):
        calls.append(payload)
        return {"id": payload["id"], "result": {"content": [{"type": "text", "text": "ok"}]}}, {}

    monkeypatch.setattr(mcp_client, "_post", fake_post)
    result = mcp_client.call_mcp_tool("server-1", "lookup", {"query": "hello"})
    assert result["result"]["content"][0]["text"] == "ok"
    assert calls[0]["method"] == "tools/call"
    assert calls[0]["params"]["name"] == "lookup"
