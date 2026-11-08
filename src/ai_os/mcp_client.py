"""Owner-triggered, read-only MCP discovery using the official SDK v2.

Discovery is deliberately separate from execution: remote tool metadata is
untrusted and is never registered as an executable local adapter.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
from urllib.parse import urlsplit


class MCPDiscoveryError(RuntimeError):
    """A configured MCP endpoint cannot be safely discovered."""


MAX_TOOLS = 50
MAX_SCHEMA_BYTES = 32 * 1024
MAX_DESCRIPTION_CHARS = 2000
MAX_SSE_EVENT_BYTES = 64 * 1024


def _endpoint(endpoint_id: str) -> dict:
    from ai_os.control_plane import list_control_plane_endpoints

    endpoint = next(
        (item for item in list_control_plane_endpoints()
         if item["endpoint_id"] == endpoint_id),
        None,
    )
    if endpoint is None:
        raise MCPDiscoveryError("MCP endpoint was not found.")
    if endpoint["protocol"] != "mcp":
        raise MCPDiscoveryError("Only MCP endpoints support MCP discovery.")
    if not endpoint["enabled"]:
        raise MCPDiscoveryError("MCP endpoint must be explicitly enabled by the owner.")
    if endpoint.get("credential_ref"):
        raise MCPDiscoveryError(
            "Authenticated MCP discovery is not enabled yet; remove no credentials "
            "or expose a read-only endpoint until the credential transport is implemented."
        )
    return endpoint


def _validate_destination(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise MCPDiscoveryError("MCP discovery requires a clean HTTPS URL without embedded credentials, query, or fragment.")
    host = parsed.hostname.rstrip(".").lower()
    allowed = {
        item.strip().rstrip(".").lower()
        for item in os.getenv("AI_OS_MCP_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    if not allowed or host not in allowed:
        raise MCPDiscoveryError(
            "MCP host is not explicitly allowlisted. Set AI_OS_MCP_ALLOWED_HOSTS "
            "to the exact hostname before discovery."
        )
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise MCPDiscoveryError("MCP hostname could not be resolved.") from exc
    if not addresses:
        raise MCPDiscoveryError("MCP hostname resolved to no addresses.")
    for address in {entry[4][0] for entry in addresses}:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise MCPDiscoveryError("MCP hostname resolves to a non-public address; discovery was blocked.")
    return url


def _tool_metadata(tool) -> dict:
    name = getattr(tool, "name", None)
    if not isinstance(name, str) or not name or len(name) > 120:
        raise MCPDiscoveryError("MCP server returned a tool with an invalid name.")
    description = getattr(tool, "description", None)
    if description is not None and not isinstance(description, str):
        description = str(description)
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = {"type": "object", "properties": {}}
    if not isinstance(schema, dict):
        raise MCPDiscoveryError("MCP tool input schema must be a JSON object.")
    try:
        encoded = json.dumps(schema, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise MCPDiscoveryError("MCP tool input schema is not valid JSON.") from exc
    if len(encoded.encode("utf-8")) > MAX_SCHEMA_BYTES:
        raise MCPDiscoveryError("MCP tool input schema exceeds the 32 KiB limit.")
    return {
        "name": name,
        "description": (description or "")[:MAX_DESCRIPTION_CHARS],
        "input_schema": schema,
        "trust": "untrusted_remote_metadata",
        "executable": False,
        "owner_approval_required_before_mapping": True,
    }


async def discover_mcp_tools(endpoint_id: str) -> dict:
    """Discover bounded metadata from one owner-enabled, allowlisted MCP server."""
    endpoint = _endpoint(endpoint_id)
    url = _validate_destination(endpoint["base_url"])
    try:
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        raise MCPDiscoveryError(
            "MCP SDK is not installed. Install the optional dependency with: "
            "pip install -e '.[mcp]'"
        ) from exc

    try:
        transport = streamable_http_client(
            url, max_sse_event_size=MAX_SSE_EVENT_BYTES
        )
        async with Client(transport) as client:
            result = await asyncio.wait_for(client.list_tools(), timeout=20)
    except asyncio.TimeoutError as exc:
        raise MCPDiscoveryError("MCP discovery timed out after 20 seconds.") from exc
    except Exception as exc:
        raise MCPDiscoveryError(
            "MCP discovery failed. Check the endpoint, TLS certificate, and server protocol."
        ) from exc

    remote_tools = list(getattr(result, "tools", []) or [])
    if len(remote_tools) > MAX_TOOLS:
        raise MCPDiscoveryError("MCP server returned more than 50 tools; discovery was rejected.")
    tools = [_tool_metadata(item) for item in remote_tools]
    names = [item["name"] for item in tools]
    if len(names) != len(set(names)):
        raise MCPDiscoveryError("MCP server returned duplicate tool names.")
    return {
        "endpoint_id": endpoint_id,
        "server_name": endpoint["name"],
        "discovered_tool_count": len(tools),
        "tools": tools,
        "execution_enabled": False,
        "notice": (
            "Discovery only. Remote descriptions and schemas are untrusted data; "
            "no tool has been granted a capability or made executable."
        ),
    }
