"""Safe, provider-neutral registry for remote MCP server configurations.

This module records configuration only. It does not make network requests, perform
OAuth, launch local processes, or store credential values.
"""
from datetime import datetime, timezone
import ipaddress
import json
import re
from urllib.parse import urlsplit
from uuid import uuid4

from ai_os.db import connect
from ai_os.schemas import MCPServerCreate

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")


def _validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("MCP endpoint must be an HTTPS URL with a hostname.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("MCP endpoint must not contain credentials or a URL fragment.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Localhost MCP endpoints are not accepted by the remote registry.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (not address.is_global):
        raise ValueError("MCP endpoint must use a globally routable host.")
    if parsed.port and parsed.port not in {443, 8443}:
        raise ValueError("MCP endpoint port must be 443 or 8443.")
    return endpoint.strip()


def _row_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "endpoint": row["endpoint"],
        "transport": row["transport"],
        "credential_env": json.loads(row["credential_env_json"]),
        "declared_capabilities": json.loads(row["capabilities_json"]),
        "enabled": bool(row["enabled"]),
        "connection_status": "not_connected",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_mcp_server(payload: MCPServerCreate) -> dict:
    endpoint = _validate_endpoint(payload.endpoint)
    env_names = sorted(set(payload.credential_env))
    if any(not _ENV_NAME.fullmatch(name) for name in env_names):
        raise ValueError("Credential references must be environment variable names, not secret values.")
    capabilities = sorted(set(item.strip() for item in payload.declared_capabilities if item.strip()))
    if len(capabilities) != len(payload.declared_capabilities):
        raise ValueError("Declared capabilities must be non-empty strings.")
    now = datetime.now(timezone.utc).isoformat()
    server_id = str(uuid4())
    try:
        with connect() as db:
            db.execute(
                """INSERT INTO mcp_servers
                (id, name, endpoint, transport, credential_env_json, capabilities_json,
                 enabled, created_at, updated_at)
                VALUES (?, ?, ?, 'streamable_http', ?, ?, ?, ?, ?)""",
                (server_id, payload.name.strip(), endpoint, json.dumps(env_names),
                 json.dumps(capabilities), int(payload.enabled), now, now),
            )
            row = db.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise ValueError("MCP endpoint is already registered.") from exc
        raise
    return _row_to_dict(row)


def list_mcp_servers() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM mcp_servers ORDER BY created_at, name").fetchall()
    return [_row_to_dict(row) for row in rows]


def set_mcp_server_enabled(server_id: str, enabled: bool) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        cursor = db.execute(
            "UPDATE mcp_servers SET enabled=?, updated_at=? WHERE id=?",
            (int(enabled), now, server_id),
        )
        if cursor.rowcount != 1:
            return None
        row = db.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
    return _row_to_dict(row)
