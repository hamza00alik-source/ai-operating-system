"""Read-only MCP Streamable HTTP connection and tool discovery.

This probe initializes a session and lists tools. It never invokes a tool.
Secrets are referenced by environment-variable name and never returned.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4

from ai_os.db import connect

_PROTOCOL_VERSION = "2025-03-26"
_TIMEOUT_SECONDS = 12


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _public_endpoint(endpoint: str) -> None:
    from urllib.parse import urlsplit
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("MCP endpoint must be HTTPS.")
    host = parsed.hostname
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise RuntimeError("MCP hostname could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("MCP endpoint resolves to a non-public IP address; connection refused.")


def _decode_response(raw: bytes, content_type: str):
    text = raw.decode("utf-8", errors="replace")
    if "text/event-stream" in content_type:
        messages = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    messages.append(json.loads(data))
        if not messages:
            raise RuntimeError("MCP server returned no JSON-RPC response.")
        return messages[-1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("MCP server returned an unsupported response format.") from exc


def _post(opener, endpoint: str, payload: dict, headers: dict):
    request = Request(endpoint, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **headers,
    }, method="POST")
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            return _decode_response(response.read(1_000_000), response.headers.get("Content-Type", "")), response.headers
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP HTTP {exc.code}: {detail[:300]}") from exc
    except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
        raise RuntimeError(f"MCP connection failed: {type(exc).__name__}") from exc


def probe_mcp_server(server_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
    if row is None:
        raise LookupError("MCP server not found.")
    if not row["enabled"]:
        raise ValueError("Enable this MCP server before testing its connection.")
    endpoint = row["endpoint"]
    _public_endpoint(endpoint)

    env_names = json.loads(row["credential_env_json"])
    missing = [name for name in env_names if not os.getenv(name)]
    if missing:
        raise ValueError("Missing configured credential environment variables: " + ", ".join(missing))
    headers = {}
    if env_names:
        # The first configured secret is sent as a bearer token; additional
        # values can be introduced as explicit auth schemes in a later version.
        headers["Authorization"] = "Bearer " + os.environ[env_names[0]]

    opener = build_opener(_NoRedirect)
    init_id = str(uuid4())
    init_payload = {
        "jsonrpc": "2.0", "id": init_id, "method": "initialize",
        "params": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "ai-operating-system", "version": "0.1.0"},
        },
    }
    response, response_headers = _post(opener, endpoint, init_payload, headers)
    if response.get("id") != init_id or "error" in response:
        raise RuntimeError("MCP initialize handshake was rejected.")
    result = response.get("result") or {}
    negotiated = result.get("protocolVersion")
    if not negotiated:
        raise RuntimeError("MCP initialize response omitted protocolVersion.")
    session_id = response_headers.get("Mcp-Session-Id")
    session_headers = {**headers, "MCP-Protocol-Version": negotiated}
    if session_id:
        session_headers["Mcp-Session-Id"] = session_id

    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    notify_request = Request(endpoint, data=json.dumps(initialized).encode(), headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        **session_headers,
    }, method="POST")
    try:
        with opener.open(notify_request, timeout=_TIMEOUT_SECONDS) as response_stream:
            response_stream.read(1000)
    except HTTPError as exc:
        raise RuntimeError(f"MCP initialized notification failed with HTTP {exc.code}.") from exc

    list_id = str(uuid4())
    listed, _ = _post(opener, endpoint, {
        "jsonrpc": "2.0", "id": list_id, "method": "tools/list", "params": {},
    }, session_headers)
    if listed.get("id") != list_id or "error" in listed:
        raise RuntimeError("MCP tools/list request failed.")
    tools = (listed.get("result") or {}).get("tools") or []
    safe_tools = [{
        "name": str(tool.get("name", ""))[:120],
        "description": str(tool.get("description", ""))[:500],
        "input_schema": tool.get("inputSchema", {}),
    } for tool in tools[:100]]
    return {
        "server_id": server_id,
        "server_name": row["name"],
        "connection_status": "connected",
        "protocol_version": negotiated,
        "server_info": result.get("serverInfo", {}),
        "tool_count": len(tools),
        "tools": safe_tools,
        "tool_execution_enabled": False,
    }
