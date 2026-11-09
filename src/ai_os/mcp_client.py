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


def _load_server(server_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
    if row is None:
        raise LookupError("MCP server not found.")
    if not row["enabled"]:
        raise ValueError("Enable this MCP server before using it.")
    env_names = json.loads(row["credential_env_json"])
    missing = [name for name in env_names if not os.getenv(name)]
    if missing:
        raise ValueError("Missing configured credential environment variables: " + ", ".join(missing))
    _public_endpoint(row["endpoint"])
    headers = {}
    if env_names:
        headers["Authorization"] = "Bearer " + os.environ[env_names[0]]
    return row, build_opener(_NoRedirect), headers


def _open_session(row, opener, headers):
    endpoint = row["endpoint"]
    init_id = str(uuid4())
    response, response_headers = _post(opener, endpoint, {
        "jsonrpc": "2.0", "id": init_id, "method": "initialize",
        "params": {"protocolVersion": _PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "ai-operating-system", "version": "0.1.0"}},
    }, headers)
    if response.get("id") != init_id or "error" in response:
        raise RuntimeError("MCP initialize handshake was rejected.")
    result = response.get("result") or {}
    negotiated = result.get("protocolVersion")
    if not negotiated:
        raise RuntimeError("MCP initialize response omitted protocolVersion.")
    session_headers = {**headers, "MCP-Protocol-Version": negotiated}
    session_id = response_headers.get("Mcp-Session-Id")
    if session_id:
        session_headers["Mcp-Session-Id"] = session_id
    notify = Request(endpoint, data=json.dumps({
        "jsonrpc": "2.0", "method": "notifications/initialized"
    }).encode(), headers={"Content-Type": "application/json",
        "Accept": "application/json, text/event-stream", **session_headers}, method="POST")
    try:
        with opener.open(notify, timeout=_TIMEOUT_SECONDS) as stream:
            stream.read(1000)
    except HTTPError as exc:
        raise RuntimeError(f"MCP initialized notification failed with HTTP {exc.code}.") from exc
    return session_headers, negotiated, result


def _list_tools(row, opener, session_headers):
    request_id = str(uuid4())
    listed, _ = _post(opener, row["endpoint"], {
        "jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {},
    }, session_headers)
    if listed.get("id") != request_id or "error" in listed:
        raise RuntimeError("MCP tools/list request failed.")
    return (listed.get("result") or {}).get("tools") or []


def probe_mcp_server(server_id: str) -> dict:
    row, opener, headers = _load_server(server_id)
    session_headers, negotiated, result = _open_session(row, opener, headers)
    tools = _list_tools(row, opener, session_headers)
    safe_tools = [{
        "name": str(tool.get("name", ""))[:120],
        "description": str(tool.get("description", ""))[:500],
        "input_schema": tool.get("inputSchema", {}),
    } for tool in tools[:100]]
    return {
        "server_id": server_id, "server_name": row["name"],
        "connection_status": "connected", "protocol_version": negotiated,
        "server_info": result.get("serverInfo", {}),
        "tool_count": len(tools), "tools": safe_tools,
        "tool_execution_enabled": True,
        "execution_policy": "owner_approval_required",
    }


def _validate_tool_arguments(schema: dict, arguments: dict) -> None:
    """Validate untrusted model arguments against the server's JSON Schema."""
    if not isinstance(schema, dict) or len(json.dumps(schema)) > 65536:
        raise ValueError("MCP tool input schema is invalid or too large.")
    if not isinstance(arguments, dict) or len(json.dumps(arguments)) > 65536:
        raise ValueError("MCP tool arguments must be a JSON object no larger than 64 KiB.")
    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        error = next(iter(validator.iter_errors(arguments)), None)
    except ImportError as exc:
        raise RuntimeError("JSON Schema validation dependency is unavailable.") from exc
    except Exception as exc:
        raise ValueError("MCP server supplied an invalid JSON Schema.") from exc
    if error is not None:
        path = ".".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"MCP tool arguments failed schema validation at {path}: {error.message[:300]}")


def _department_tool_allowlist(department: str | None) -> set[str]:
    """Return exact server-id:tool-name grants; default-deny for agent departments."""
    if not department:
        return set()
    raw = os.getenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", "{}")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST must be valid JSON.") from exc
    if not isinstance(config, dict):
        raise ValueError("MCP department allowlist must be a JSON object.")
    entries = config.get(department, [])
    if not isinstance(entries, list) or any(
        not isinstance(item, str) or ":" not in item or len(item) > 256 for item in entries
    ):
        raise ValueError(f"MCP allowlist for department {department!r} must be a list of server-id:tool-name entries.")
    return set(entries)


def call_mcp_tool(server_id: str, tool_name: str, arguments: dict) -> dict:
    """Invoke one remote tool; caller must consume a matching one-time approval first."""
    row, opener, headers = _load_server(server_id)
    session_headers, negotiated, _ = _open_session(row, opener, headers)
    tools = _list_tools(row, opener, session_headers)
    match = next((tool for tool in tools if tool.get("name") == tool_name), None)
    if match is None:
        raise LookupError("Requested tool is not currently advertised by this MCP server.")
    schema = match.get("inputSchema") or {"type": "object", "properties": {}}
    _validate_tool_arguments(schema, arguments)
    request_id = str(uuid4())
    result, _ = _post(opener, row["endpoint"], {
        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }, session_headers)
    if result.get("id") != request_id:
        raise RuntimeError("MCP tool response did not match the request.")
    if "error" in result:
        raise RuntimeError("MCP tool execution failed: " + str(result["error"])[:500])
    return {"server_id": server_id, "tool_name": tool_name,
            "protocol_version": negotiated, "result": result.get("result")}


def discover_enabled_tool_catalog(department: str | None = None) -> list[dict]:
    """Discover only tools explicitly granted to this department; default-deny."""
    allowed = _department_tool_allowlist(department)
    if not allowed:
        return []
    with connect() as db:
        rows = db.execute(
            "SELECT id,name FROM mcp_servers WHERE enabled=1 ORDER BY name,id"
        ).fetchall()
    catalog = []
    for row in rows:
        prefix = row["id"] + ":"
        if not any(entry.startswith(prefix) for entry in allowed):
            continue
        discovered = probe_mcp_server(row["id"])
        for tool in discovered["tools"]:
            if f"{row['id']}:{tool['name']}" not in allowed:
                continue
            catalog.append({
                "server_id": row["id"],
                "server_name": row["name"],
                "tool_name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema") or {"type": "object", "properties": {}},
            })
    return catalog
