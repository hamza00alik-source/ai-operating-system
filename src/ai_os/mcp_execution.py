"""Owner-approved, read-only MCP tool execution.

Execution is a separate owner-triggered action. A proposal approval alone never
executes a tool. Every execution is one-time, schema-bound, and audited.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ai_os.db import connect
from ai_os.mcp_client import _load_server, _open_session, _list_tools, _post
from ai_os.mcp_tool_catalog import get_discovered_tool_schema, validate_discovered_tool_arguments


def _read_only_grants() -> set[str]:
    raw = os.getenv("AI_OS_MCP_READ_ONLY_TOOLS", "").strip()
    if not raw:
        return set()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AI_OS_MCP_READ_ONLY_TOOLS must be valid JSON; execution is disabled.") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) or ":" not in item for item in value):
        raise ValueError("AI_OS_MCP_READ_ONLY_TOOLS must be a JSON list of exact server-id:tool-name IDs.")
    return set(value)


def execute_approved_proposal(proposal_id: str) -> dict:
    """Execute one approved proposal only after fresh read-only and schema checks."""
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM mcp_tool_proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None:
            raise LookupError("MCP tool proposal not found.")
        if row["status"] != "approved":
            raise ValueError("Only an approved proposal can be executed.")
        if row["risk_level"] != "low":
            raise PermissionError("Only low-risk read proposals may be executed.")
        if row["execution_status"] is not None:
            raise ValueError("This approval has already been consumed or attempted; execution cannot be replayed.")
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            raise ValueError("Proposal approval has expired.")
        server_id, tool_name = row["server_id"], row["tool_name"]
        tool_id = f"{server_id}:{tool_name}"
        if tool_id not in _read_only_grants():
            raise PermissionError("Tool is not explicitly configured in AI_OS_MCP_READ_ONLY_TOOLS.")
        args = json.loads(row["arguments_json"])
        proposal_fingerprint = row["fingerprint"]
        expected_schema = row["schema_sha256"]
        department = row["department"]
        raw_allowlist = os.getenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", "{}")
        try:
            dept_allowlist = json.loads(raw_allowlist)
        except json.JSONDecodeError as exc:
            raise PermissionError("Department tool allowlist is invalid; execution is blocked.") from exc
        if tool_id not in dept_allowlist.get(department, []):
            raise PermissionError("Tool is no longer allowlisted for this department.")
        changed = db.execute(
            """UPDATE mcp_tool_proposals SET execution_status='running',
            execution_started_at=? WHERE id=? AND status='approved' AND execution_status IS NULL""",
            (now, proposal_id),
        ).rowcount
        if changed != 1:
            raise ValueError("Approval was consumed concurrently; refresh the inbox.")
        db.execute(
            """INSERT INTO audit_events
            (event_type,actor_id,resource_type,resource_id,details_json,created_at)
            VALUES(?,?,?,?,?,?)""",
            ("mcp_tool.execution_started", "owner", "mcp_tool_proposal", proposal_id,
             json.dumps({"server_id": server_id, "tool_name": tool_name,
                         "fingerprint": proposal_fingerprint}, sort_keys=True), now),
        )

    result = None
    failure = None
    try:
        schema_record = get_discovered_tool_schema(server_id, tool_name)
        if schema_record is None or schema_record["schema_sha256"] != expected_schema:
            raise PermissionError("Discovered tool schema changed or is unavailable; rediscover and approve again.")
        if validate_discovered_tool_arguments(server_id, tool_name, args) != expected_schema:
            raise PermissionError("Approved arguments no longer match the discovered schema.")
        row_server, opener, headers = _load_server(server_id)
        session_headers, _version, _info = _open_session(row_server, opener, headers)
        fresh_tools = _list_tools(row_server, opener, session_headers)
        matches = [item for item in fresh_tools if item.get("name") == tool_name]
        if len(matches) != 1:
            raise PermissionError("Tool is missing or ambiguous in fresh server discovery.")
        fresh = matches[0]
        annotations = fresh.get("annotations") or {}
        if annotations.get("readOnlyHint") is not True:
            raise PermissionError("MCP server did not explicitly mark this tool read-only.")
        fresh_schema = fresh.get("inputSchema") or {"type": "object", "properties": {}}
        if fresh_schema != schema_record["schema"]:
            raise PermissionError("Live MCP tool schema differs from the owner-discovered schema.")
        response, _headers = _post(opener, row_server["endpoint"], {
            "jsonrpc": "2.0", "id": "aios-owner-approved-call",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }, session_headers)
        if response.get("id") != "aios-owner-approved-call" or "error" in response:
            raise RuntimeError("MCP tools/call returned an invalid or error response.")
        result = response.get("result") or {}
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 900_000:
            raise RuntimeError("MCP tool result exceeded the 900 KiB storage limit.")
        if result.get("isError"):
            raise RuntimeError("MCP tool reported an execution error.")
    except Exception as exc:
        failure = f"{type(exc).__name__}: {str(exc)[:500]}"

    finished = datetime.now(timezone.utc).isoformat()
    status = "failed" if failure else "succeeded"
    details = {"server_id": server_id, "tool_name": tool_name, "status": status,
               "fingerprint": proposal_fingerprint}
    if failure:
        details["error"] = failure
    else:
        details["result"] = result
    with connect() as db:
        db.execute(
            "UPDATE mcp_tool_proposals SET execution_status=?,execution_finished_at=? WHERE id=? AND execution_status='running'",
            (status, finished, proposal_id),
        )
        db.execute(
            """INSERT INTO audit_events
            (event_type,actor_id,resource_type,resource_id,details_json,created_at)
            VALUES(?,?,?,?,?,?)""",
            ("mcp_tool.execution_" + status, "owner", "mcp_tool_proposal", proposal_id,
             json.dumps(details, ensure_ascii=False, sort_keys=True), finished),
        )
    if failure:
        raise RuntimeError(failure)
    return {"proposal_id": proposal_id, "execution_status": status, "result": result,
            "side_effect_policy": "read-only annotation required; no write-capable tools enabled"}
