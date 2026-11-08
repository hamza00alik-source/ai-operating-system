"""Owner-approved, read-only MCP tool broker.

Discovery metadata is untrusted. A tool becomes callable only after an owner
explicitly maps it as read-only and grants an agent the mcp.read capability.
Write-capable tools are deliberately not supported by this broker.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect


class MCPBrokerError(RuntimeError):
    """A remote MCP tool mapping or execution was rejected."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_mcp_broker_storage() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS mcp_discovered_tools (
            endpoint_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            input_schema_json TEXT NOT NULL,
            discovered_at TEXT NOT NULL,
            PRIMARY KEY(endpoint_id, tool_name)
        );
        CREATE TABLE IF NOT EXISTS mcp_tool_mappings (
            mapping_id TEXT PRIMARY KEY,
            endpoint_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            access_mode TEXT NOT NULL CHECK(access_mode='read_only'),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(endpoint_id, tool_name)
        );
        CREATE INDEX IF NOT EXISTS idx_mcp_tool_mappings_enabled
            ON mcp_tool_mappings(endpoint_id, enabled);
        """)


def save_discovered_tools(endpoint_id: str, tools: list[dict]) -> None:
    now = _now()
    with connect() as db:
        for tool in tools:
            db.execute(
                """INSERT INTO mcp_discovered_tools
                   (endpoint_id, tool_name, description, input_schema_json, discovered_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(endpoint_id, tool_name) DO UPDATE SET
                     description=excluded.description,
                     input_schema_json=excluded.input_schema_json,
                     discovered_at=excluded.discovered_at""",
                (
                    endpoint_id, tool["name"], tool.get("description", "")[:2000],
                    json.dumps(tool.get("input_schema", {}), ensure_ascii=False),
                    now,
                ),
            )


def list_discovered_tools(endpoint_id: str | None = None) -> list[dict]:
    with connect() as db:
        if endpoint_id:
            rows = db.execute(
                """SELECT * FROM mcp_discovered_tools WHERE endpoint_id=?
                   ORDER BY tool_name""", (endpoint_id,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM mcp_discovered_tools ORDER BY endpoint_id, tool_name"
            ).fetchall()
    return [{
        "endpoint_id": row["endpoint_id"],
        "name": row["tool_name"],
        "description": row["description"],
        "input_schema": json.loads(row["input_schema_json"]),
        "discovered_at": row["discovered_at"],
        "trust": "untrusted_remote_metadata",
        "executable": False,
    } for row in rows]


def create_read_only_mapping(
    *, endpoint_id: str, tool_name: str, owner_confirmed_read_only: bool,
    approved_by: str,
) -> dict:
    if owner_confirmed_read_only is not True:
        raise MCPBrokerError("Owner must explicitly confirm that this remote tool is read-only.")
    tool_name = tool_name.strip()
    if not tool_name or len(tool_name) > 120:
        raise MCPBrokerError("Remote tool name is invalid.")
    from ai_os.control_plane import list_control_plane_endpoints
    endpoint = next(
        (item for item in list_control_plane_endpoints()
         if item["endpoint_id"] == endpoint_id), None
    )
    if endpoint is None or endpoint["protocol"] != "mcp" or not endpoint["enabled"]:
        raise MCPBrokerError("An existing owner-enabled MCP endpoint is required.")
    with connect() as db:
        discovered = db.execute(
            """SELECT tool_name FROM mcp_discovered_tools
               WHERE endpoint_id=? AND tool_name=?""",
            (endpoint_id, tool_name),
        ).fetchone()
        if discovered is None:
            raise MCPBrokerError("Tool must be discovered before it can be mapped.")
        now = _now()
        mapping_id = str(uuid4())
        db.execute(
            """INSERT INTO mcp_tool_mappings
               (mapping_id, endpoint_id, tool_name, access_mode, enabled,
                approved_by, approved_at, created_at)
               VALUES (?, ?, ?, 'read_only', 1, ?, ?, ?)
               ON CONFLICT(endpoint_id, tool_name) DO UPDATE SET
                 access_mode='read_only', enabled=1, approved_by=excluded.approved_by,
                 approved_at=excluded.approved_at""",
            (mapping_id, endpoint_id, tool_name, approved_by[:120], now, now),
        )
        row = db.execute(
            """SELECT * FROM mcp_tool_mappings
               WHERE endpoint_id=? AND tool_name=?""",
            (endpoint_id, tool_name),
        ).fetchone()
    return _mapping_row(row)


def _mapping_row(row) -> dict:
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    item["executable"] = item["enabled"] and item["access_mode"] == "read_only"
    return item


def list_mcp_tool_mappings(*, endpoint_id: str | None = None) -> list[dict]:
    with connect() as db:
        if endpoint_id:
            rows = db.execute(
                "SELECT * FROM mcp_tool_mappings WHERE endpoint_id=? ORDER BY created_at",
                (endpoint_id,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM mcp_tool_mappings ORDER BY created_at"
            ).fetchall()
    return [_mapping_row(row) for row in rows]


def set_mcp_tool_mapping_enabled(mapping_id: str, enabled: bool) -> dict | None:
    with connect() as db:
        db.execute(
            "UPDATE mcp_tool_mappings SET enabled=? WHERE mapping_id=?",
            (1 if enabled else 0, mapping_id),
        )
        row = db.execute(
            "SELECT * FROM mcp_tool_mappings WHERE mapping_id=?", (mapping_id,)
        ).fetchone()
    return _mapping_row(row) if row else None


def get_mcp_tool_mapping(mapping_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM mcp_tool_mappings WHERE mapping_id=?", (mapping_id,)
        ).fetchone()
    return _mapping_row(row) if row else None
