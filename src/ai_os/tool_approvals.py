"""Persisted, fail-closed approval inbox for proposed MCP tool calls.

This module deliberately does not execute tools. Approval records only authorize a
future, separately implemented execution layer; they are not execution credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_os.db import connect

MAX_ARGUMENT_BYTES = 64 * 1024
DEFAULT_TTL_MINUTES = 30
RISK_LEVELS = {"read": "low", "write": "high", "financial": "critical", "external": "critical"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(server_id: str, tool_name: str, arguments: dict) -> str:
    canonical = json.dumps(
        {"server_id": server_id, "tool_name": tool_name, "arguments": arguments},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _department_allowlist() -> dict:
    raw = os.getenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Department tool allowlist is invalid JSON; all proposals are blocked.") from exc
    if not isinstance(value, dict) or any(
        not isinstance(k, str) or not isinstance(v, list)
        or any(not isinstance(item, str) for item in v)
        for k, v in value.items()
    ):
        raise ValueError("Department tool allowlist must map department names to tool ID lists.")
    return value


def department_tool_catalog(department: str) -> list[str]:
    """Return configured server:tool identifiers only; never reads credentials."""
    return sorted(_department_allowlist().get(department, []))


def _ensure_table(db) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS mcp_tool_proposals (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            department TEXT NOT NULL,
            server_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments_json TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','rejected','expired')),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_mcp_tool_proposals_status ON mcp_tool_proposals(status, created_at)")


def propose_tool_call(*, run_id: str, task_id: str, department: str,
                      server_id: str, tool_name: str, arguments: dict,
                      risk_level: str = "read", ttl_minutes: int = DEFAULT_TTL_MINUTES) -> dict:
    """Persist a worker-generated proposal only when explicitly allowlisted."""
    if risk_level not in RISK_LEVELS.values():
        raise ValueError("Unknown risk level; proposal rejected.")
    if not all(isinstance(v, str) and v.strip() for v in (run_id, task_id, department, server_id, tool_name)):
        raise ValueError("Proposal identifiers and tool name are required.")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_ARGUMENT_BYTES:
        raise ValueError("Tool arguments exceed the 64 KiB proposal limit.")
    allowed = _department_allowlist().get(department, [])
    tool_id = f"{server_id}:{tool_name}"
    if tool_id not in allowed:
        raise PermissionError("Tool is not allowlisted for this department; proposal was not stored.")
    now = _now()
    ttl = max(1, min(int(ttl_minutes), 1440))
    proposal_id = str(uuid4())
    fingerprint = _fingerprint(server_id, tool_name, arguments)
    with connect() as db:
        _ensure_table(db)
        db.execute(
            """INSERT INTO mcp_tool_proposals
            (id,run_id,task_id,department,server_id,tool_name,arguments_json,
             fingerprint,risk_level,status,created_at,expires_at)
            VALUES(?,?,?,?,?,?,?,?,?,'pending',?,?)""",
            (proposal_id, run_id, task_id, department, server_id, tool_name,
             encoded, fingerprint, risk_level, now.isoformat(),
             (now + timedelta(minutes=ttl)).isoformat()),
        )
    return {"id": proposal_id, "status": "pending", "risk_level": risk_level,
            "fingerprint": fingerprint, "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
            "execution_enabled": False}


def list_tool_proposals() -> list[dict]:
    with connect() as db:
        _ensure_table(db)
        rows = db.execute(
            "SELECT * FROM mcp_tool_proposals ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    result = []
    now = _now()
    for row in rows:
        item = dict(row)
        if item["status"] == "pending" and datetime.fromisoformat(item["expires_at"]) <= now:
            with connect() as db:
                db.execute(
                    "UPDATE mcp_tool_proposals SET status='expired' WHERE id=? AND status='pending'",
                    (item["id"],),
                )
            item["status"] = "expired"
        item["arguments"] = json.loads(item.pop("arguments_json"))
        item["execution_enabled"] = False
        result.append(item)
    return result


def decide_tool_proposal(proposal_id: str, decision: str, actor: str = "owner") -> dict | None:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    now = _now()
    with connect() as db:
        _ensure_table(db)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM mcp_tool_proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None:
            return None
        if row["status"] != "pending":
            raise ValueError("Proposal is no longer pending; decisions are one-time.")
        if datetime.fromisoformat(row["expires_at"]) <= now:
            db.execute("UPDATE mcp_tool_proposals SET status='expired' WHERE id=? AND status='pending'", (proposal_id,))
            expired = True
        else:
            expired = False
        if expired:
            result = None
        else:
            changed = db.execute(
                """UPDATE mcp_tool_proposals SET status=?,decided_at=?,decided_by=?
                WHERE id=? AND status='pending' AND fingerprint=?""",
                (decision, now.isoformat(), actor, proposal_id, row["fingerprint"]),
            ).rowcount
            if changed != 1:
                raise ValueError("Proposal changed concurrently; refresh the approval inbox.")
            result = dict(db.execute("SELECT * FROM mcp_tool_proposals WHERE id=?", (proposal_id,)).fetchone())
    if result is None:
        raise ValueError("Proposal has expired.")
    result["arguments"] = json.loads(result.pop("arguments_json"))
    result["execution_enabled"] = False
    return result
