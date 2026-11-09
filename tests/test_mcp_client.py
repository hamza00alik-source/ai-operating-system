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


def fake_row(enabled=True, credentials="[]"):
    return {
        "id": "server-1",
        "name": "Example MCP",
        "endpoint": "https://mcp.example.com/mcp",
        "enabled": int(enabled),
        "credential_env_json": credentials,
    }


def install_row(monkeypatch, row):
    @contextmanager
    def fake_connect():
        yield FakeDB(row)
    monkeypatch.setattr(mcp_client, "connect", fake_connect)


def test_mcp_probe_refuses_disabled_server(monkeypatch):
    install_row(monkeypatch, fake_row(enabled=False))
    with pytest.raises(ValueError, match="Enable"):
        mcp_client.probe_mcp_server("server-1")


def test_mcp_probe_refuses_missing_credential_without_network(monkeypatch):
    install_row(monkeypatch, fake_row(credentials='["AIOS_TEST_MCP_TOKEN"]'))
    monkeypatch.delenv("AIOS_TEST_MCP_TOKEN", raising=False)
    monkeypatch.setattr(mcp_client, "_public_endpoint", lambda _endpoint: pytest.fail("network validation should not run"))
    with pytest.raises(ValueError, match="Missing configured credential"):
        mcp_client.probe_mcp_server("server-1")


def test_mcp_probe_rejects_private_dns_resolution(monkeypatch):
    install_row(monkeypatch, fake_row())
    monkeypatch.setattr(mcp_client.socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("127.0.0.1", 443))
    ])
    with pytest.raises(ValueError, match="non-public IP"):
        mcp_client.probe_mcp_server("server-1")


def test_sse_json_rpc_response_is_decoded():
    payload = b": keepalive\ndata: {\"jsonrpc\":\"2.0\",\"id\":\"abc\",\"result\":{\"tools\":[]}}\n\n"
    result = mcp_client._decode_response(payload, "text/event-stream")
    assert result["id"] == "abc"
    assert result["result"]["tools"] == []



def test_tool_arguments_are_checked_against_full_json_schema():
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 3}},
        "required": ["query"],
        "additionalProperties": False,
    }
    mcp_client._validate_tool_arguments(schema, {"query": "market"})
    with pytest.raises(ValueError, match="schema validation"):
        mcp_client._validate_tool_arguments(schema, {"query": "x"})
    with pytest.raises(ValueError, match="schema validation"):
        mcp_client._validate_tool_arguments(schema, {"query": "market", "admin": True})


def test_invalid_server_json_schema_is_rejected():
    with pytest.raises(ValueError, match="invalid JSON Schema"):
        mcp_client._validate_tool_arguments({"type": "not-a-json-schema-type"}, {})


def test_department_tool_allowlist_defaults_to_deny(monkeypatch):
    monkeypatch.delenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", raising=False)
    assert mcp_client._department_tool_allowlist("research") == set()


def test_department_tool_allowlist_returns_only_exact_grants(monkeypatch):
    monkeypatch.setenv(
        "AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST",
        '{"research":["server-1:search"],"marketing":[]}',
    )
    assert mcp_client._department_tool_allowlist("research") == {"server-1:search"}
    assert mcp_client._department_tool_allowlist("marketing") == set()


def test_malformed_department_allowlist_fails_closed(monkeypatch):
    monkeypatch.setenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", "not-json")
    with pytest.raises(ValueError, match="valid JSON"):
        mcp_client._department_tool_allowlist("research")



def test_agent_tool_discovery_does_not_query_servers_without_grants(monkeypatch):
    monkeypatch.setattr(mcp_client, "_department_tool_allowlist", lambda _department: set())
    monkeypatch.setattr(mcp_client, "connect", lambda: pytest.fail("no server should be queried"))
    assert mcp_client.discover_enabled_tool_catalog("research") == []
