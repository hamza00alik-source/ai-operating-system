"""Owner-reviewed, persisted MCP tool schemas.

Schemas are captured only by the owner-triggered read-only discovery route. This
module never connects to a server and never invokes a tool.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ai_os.db import connect

MAX_SCHEMA_BYTES = 64 * 1024


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _schema_digest(schema: dict) -> str:
    return hashlib.sha256(_canonical(schema).encode("utf-8")).hexdigest()


def _check_schema(schema: dict) -> str:
    if not isinstance(schema, dict):
        raise ValueError("MCP tool input schema must be a JSON object.")
    encoded = _canonical(schema)
    if len(encoded.encode("utf-8")) > MAX_SCHEMA_BYTES:
        raise ValueError("MCP tool input schema exceeds the 64 KiB limit.")

    def reject_remote_refs(value):
        if isinstance(value, dict):
            if "$ref" in value or "$dynamicRef" in value:
                raise ValueError("MCP tool schemas containing references are not accepted.")
            for child in value.values():
                reject_remote_refs(child)
        elif isinstance(value, list):
            for child in value:
                reject_remote_refs(child)

    reject_remote_refs(schema)
    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
    except ImportError as exc:
        raise RuntimeError("JSON Schema validation dependency is unavailable.") from exc
    except Exception as exc:
        raise ValueError("MCP server supplied an invalid JSON Schema.") from exc
    return encoded


def _ensure_table(db) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS mcp_discovered_tools (
            server_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            input_schema_json TEXT NOT NULL,
            schema_sha256 TEXT NOT NULL,
            discovered_at TEXT NOT NULL,
            PRIMARY KEY(server_id, tool_name)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_mcp_discovered_tools_server ON mcp_discovered_tools(server_id, tool_name)")


def persist_discovered_tools(server_id: str, tools: list[dict]) -> dict:
    """Replace a server's stored catalogue after an owner-triggered discovery."""
    if not isinstance(tools, list) or len(tools) > 100:
        raise ValueError("MCP discovery returned an invalid tool catalogue.")
    prepared = []
    seen = set()
    now = datetime.now(timezone.utc).isoformat()
    for tool in tools:
        if not isinstance(tool, dict):
            raise ValueError("MCP discovery returned an invalid tool entry.")
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 120 or name in seen:
            raise ValueError("MCP tool names must be unique non-empty strings of at most 120 characters.")
        seen.add(name)
        schema = tool.get("input_schema") or {"type": "object", "properties": {}}
        encoded = _check_schema(schema)
        prepared.append((server_id, name, str(tool.get("description", ""))[:500],
                         encoded, _schema_digest(schema), now))
    with connect() as db:
        _ensure_table(db)
        server = db.execute("SELECT enabled FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
        if server is None or not server["enabled"]:
            raise ValueError("MCP server must exist and be enabled before saving discovered tools.")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM mcp_discovered_tools WHERE server_id=?", (server_id,))
        db.executemany(
            """INSERT INTO mcp_discovered_tools
            (server_id,tool_name,description,input_schema_json,schema_sha256,discovered_at)
            VALUES(?,?,?,?,?,?)""",
            prepared,
        )
        db.execute(
            """INSERT INTO audit_events
            (event_type,actor_id,resource_type,resource_id,details_json,created_at)
            VALUES(?,?,?,?,?,?)""",
            ("mcp_tool_catalog.discovered", "owner", "mcp_server", server_id,
             json.dumps({"tool_count": len(prepared),
                         "schema_fingerprints": {item[1]: item[4] for item in prepared}},
                        sort_keys=True, separators=(",", ":")), now),
        )
    return {"server_id": server_id, "tool_count": len(prepared),
            "schema_fingerprints": {item[1]: item[4] for item in prepared}}


def get_discovered_tool_schema(server_id: str, tool_name: str) -> dict | None:
    with connect() as db:
        _ensure_table(db)
        row = db.execute(
            """SELECT t.input_schema_json,t.schema_sha256,t.discovered_at
            FROM mcp_discovered_tools t JOIN mcp_servers s ON s.id=t.server_id
            WHERE t.server_id=? AND t.tool_name=? AND s.enabled=1""",
            (server_id, tool_name),
        ).fetchone()
    if row is None:
        return None
    schema = json.loads(row["input_schema_json"])
    if _schema_digest(schema) != row["schema_sha256"]:
        raise ValueError("Stored MCP tool schema fingerprint does not match; rediscover and review it.")
    return {"schema": schema, "schema_sha256": row["schema_sha256"],
            "discovered_at": row["discovered_at"]}


def validate_discovered_tool_arguments(server_id: str, tool_name: str, arguments: dict) -> str:
    record = get_discovered_tool_schema(server_id, tool_name)
    if record is None:
        raise PermissionError("Tool has no current owner-discovered schema for an enabled server.")
    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator(record["schema"]).validate(arguments)
    except ImportError as exc:
        raise RuntimeError("JSON Schema validation dependency is unavailable.") from exc
    except Exception as exc:
        raise ValueError("Tool arguments do not satisfy the owner-discovered JSON Schema.") from exc
    return record["schema_sha256"]
