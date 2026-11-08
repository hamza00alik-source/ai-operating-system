"""Safe MCP server registry metadata.

This module intentionally does not launch subprocesses or make network calls.
It exposes a validated, disabled-by-default connection manifest so a later MCP
client can enforce transport, credential, tool-allowlist, and approval policy.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse


class MCPRegistryError(ValueError):
    """Invalid MCP registry configuration."""


def _load_manifest() -> list[dict]:
    raw = os.getenv("AI_OS_MCP_SERVERS_JSON", "").strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise MCPRegistryError("AI_OS_MCP_SERVERS_JSON must contain valid JSON.") from None
    if not isinstance(value, list):
        raise MCPRegistryError("MCP server configuration must be a JSON array.")
    return value


def list_mcp_servers() -> list[dict]:
    """Return sanitized server metadata; never return credential values."""
    servers = []
    seen = set()
    for item in _load_manifest():
        if not isinstance(item, dict):
            raise MCPRegistryError("Each MCP server entry must be an object.")
        server_id = item.get("id")
        name = item.get("name")
        transport = item.get("transport")
        if not isinstance(server_id, str) or not server_id or len(server_id) > 80:
            raise MCPRegistryError("Each MCP server requires a short non-empty id.")
        if server_id in seen:
            raise MCPRegistryError("MCP server ids must be unique.")
        seen.add(server_id)
        if not isinstance(name, str) or not name or len(name) > 120:
            raise MCPRegistryError(f"MCP server {server_id} requires a name.")
        if transport not in {"streamable_http", "sse"}:
            raise MCPRegistryError(
                f"MCP server {server_id} uses an unsupported transport. "
                "Only streamable_http and sse are accepted by this registry."
            )
        endpoint = item.get("endpoint")
        parsed = urlparse(endpoint or "")
        if parsed.scheme != "https" or not parsed.netloc:
            raise MCPRegistryError(f"MCP server {server_id} requires an HTTPS endpoint.")
        allowed_tools = item.get("allowed_tools", [])
        if not isinstance(allowed_tools, list) or any(
            not isinstance(tool, str) or not tool or len(tool) > 120
            for tool in allowed_tools
        ):
            raise MCPRegistryError(f"MCP server {server_id} has an invalid tool allowlist.")
        credential_env = item.get("credential_env")
        if credential_env is not None and (
            not isinstance(credential_env, str)
            or not credential_env.startswith("AI_OS_")
            or len(credential_env) > 120
        ):
            raise MCPRegistryError(f"MCP server {server_id} has an invalid credential_env name.")
        enabled = item.get("enabled", False)
        if not isinstance(enabled, bool):
            raise MCPRegistryError(f"MCP server {server_id} enabled must be a boolean.")
        servers.append({
            "id": server_id,
            "name": name,
            "transport": transport,
            "endpoint": endpoint,
            "enabled": enabled,
            "connection_ready": bool(
                enabled and (not credential_env or os.getenv(credential_env))
            ),
            "credential": (
                "configured" if credential_env and os.getenv(credential_env)
                else "not_configured" if credential_env
                else "not_required"
            ),
            "allowed_tools": list(allowed_tools),
            "approval_required": True,
            "execution_available": False,
            "note": "Registry only; MCP connections and tool calls are not enabled yet.",
        })
    return servers
