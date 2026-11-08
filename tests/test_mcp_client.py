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
