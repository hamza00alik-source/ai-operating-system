"""Persisted, fail-closed approval inbox for proposed MCP tool calls.

This module deliberately does not execute tools. Approval records only authorize a
future, separately implemented execution layer; they are not execution credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.mcp_tool_catalog import validate_discovered_tool_arguments

MAX_ARGUMENT_BYTES = 64 * 1024
DEFAULT_TTL_MINUTES = 30
RISK_LEVELS = {"read": "low", "write": "high", "financial": "critical", "external": "critical"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(server_id: str, tool_name: str, arguments: dict, schema_sha256: str) -> str:
    canonical = json.dumps(
        {"server_id": server_id, "tool_name": tool_name, "arguments": arguments, "schema_sha256": schema_sha256},
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
            schema_sha256 TEXT NOT NULL DEFAULT '',
            risk_level TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','rejected','expired')),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT
        )
    """)
    columns = {row["name"] for row in db.execute("PRAGMA table_info(mcp_tool_proposals)")}
    if "schema_sha256" not in columns:
        db.execute("ALTER TABLE mcp_tool_proposals ADD COLUMN schema_sha256 TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mcp_tool_proposals_status ON mcp_tool_proposals(status, created_at)")


def propose_tool_call(*, run_id: str, task_id: str, department: str,
                      server_id: str, tool_name: str, arguments: dict,
                      risk_level: str = "read", ttl_minutes: int = DEFAULT_TTL_MINUTES) -> dict:
    """Persist a worker-generated proposal only when explicitly allowlisted."""
    if risk_level not in RISK_LEVELS:
        raise ValueError("Unknown risk classification; proposal rejected.")
    risk_level = RISK_LEVELS[risk_level]
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
    schema_sha256 = validate_discovered_tool_arguments(server_id, tool_name, arguments)
    fingerprint = _fingerprint(server_id, tool_name, arguments, schema_sha256)
    with connect() as db:
        _ensure_table(db)
        db.execute(
            """INSERT INTO mcp_tool_proposals
            (id,run_id,task_id,department,server_id,tool_name,arguments_json,
             fingerprint,schema_sha256,risk_level,status,created_at,expires_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?)""",
            (proposal_id, run_id, task_id, department, server_id, tool_name,
             encoded, fingerprint, schema_sha256, risk_level, now.isoformat(),
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
        # Re-check the live enabled-server catalogue at decision time. A schema
        # refresh or server disable invalidates the proposal before approval.
        current_schema_sha256 = validate_discovered_tool_arguments(
            row["server_id"], row["tool_name"], json.loads(row["arguments_json"])
        )
        if current_schema_sha256 != row["schema_sha256"]:
            raise ValueError("Tool schema changed after proposal creation; reject and request a fresh proposal.")
        allowed = _department_allowlist().get(row["department"], [])
        if f'{row["server_id"]}:{row["tool_name"]}' not in allowed:
            raise PermissionError("Tool is no longer allowlisted for this department.")
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
                WHERE id=? AND status='pending' AND fingerprint=? AND schema_sha256=?""",
                (decision, now.isoformat(), actor, proposal_id, row["fingerprint"], current_schema_sha256),
            ).rowcount
            if changed != 1:
                raise ValueError("Proposal changed concurrently; refresh the approval inbox.")
            db.execute(
                """INSERT INTO audit_events
                (event_type,actor_id,resource_type,resource_id,details_json,created_at)
                VALUES(?,?,?,?,?,?)""",
                ("mcp_tool_proposal.decision", actor, "mcp_tool_proposal", proposal_id,
                 json.dumps({"decision": decision, "fingerprint": row["fingerprint"],
                             "schema_sha256": current_schema_sha256},
                            sort_keys=True, separators=(",", ":")), now.isoformat()),
            )
            result = dict(db.execute("SELECT * FROM mcp_tool_proposals WHERE id=?", (proposal_id,)).fetchone())
    if result is None:
        raise ValueError("Proposal has expired.")
    result["arguments"] = json.loads(result.pop("arguments_json"))
    result["execution_enabled"] = False
    return result


def reserve_approved_tool_proposal(proposal_id: str, actor: str = "owner") -> dict:
    """Atomically reserve an approved proposal once; this never invokes an MCP tool.

    A reservation is an auditable, one-time authorization checkpoint for a future
    isolated executor. It deliberately does not load credentials, perform network
    I/O, alter the proposal decision, or enable execution.
    """
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ValueError("Proposal ID is required.")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("Reservation actor is required.")

    now = _now()
    with connect() as db:
        _ensure_table(db)
        db.execute("""
            CREATE TABLE IF NOT EXISTS mcp_tool_execution_reservations (
                id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL UNIQUE,
                proposal_fingerprint TEXT NOT NULL,
                schema_sha256 TEXT NOT NULL,
                reserved_at TEXT NOT NULL,
                reserved_by TEXT NOT NULL
            )
        """)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM mcp_tool_proposals WHERE id=?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise LookupError("Proposal was not found.")
        if row["status"] != "approved":
            raise PermissionError("Only an approved proposal can be reserved.")
        if datetime.fromisoformat(row["expires_at"]) <= now:
            raise ValueError("Approved proposal has expired.")
        arguments = json.loads(row["arguments_json"])
        expected_fingerprint = _fingerprint(
            row["server_id"], row["tool_name"], arguments, row["schema_sha256"]
        )
        if expected_fingerprint != row["fingerprint"]:
            raise ValueError("Proposal fingerprint integrity check failed.")

        # Validate against the current enabled-server catalogue within the same
        # transaction, avoiding a time-of-check/time-of-use gap.
        schema_row = db.execute(
            """SELECT t.input_schema_json,t.schema_sha256
            FROM mcp_discovered_tools t JOIN mcp_servers s ON s.id=t.server_id
            WHERE t.server_id=? AND t.tool_name=? AND s.enabled=1""",
            (row["server_id"], row["tool_name"]),
        ).fetchone()
        if schema_row is None:
            raise PermissionError("Tool has no current schema on an enabled server.")
        schema = json.loads(schema_row["input_schema_json"])
        schema_digest = hashlib.sha256(
            json.dumps(schema, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if schema_digest != schema_row["schema_sha256"] or schema_digest != row["schema_sha256"]:
            raise ValueError("Tool schema changed or failed integrity validation.")
        try:
            from jsonschema import Draft202012Validator
            Draft202012Validator(schema).validate(arguments)
        except ImportError as exc:
            raise RuntimeError("JSON Schema validation dependency is unavailable.") from exc
        except Exception as exc:
            raise ValueError("Approved arguments no longer satisfy the current tool schema.") from exc

        allowed = _department_allowlist().get(row["department"], [])
        if f'{row["server_id"]}:{row["tool_name"]}' not in allowed:
            raise PermissionError("Tool is no longer allowlisted for this department.")

        reservation_id = str(uuid4())
        try:
            db.execute(
                """INSERT INTO mcp_tool_execution_reservations
                (id,proposal_id,proposal_fingerprint,schema_sha256,reserved_at,reserved_by)
                VALUES(?,?,?,?,?,?)""",
                (reservation_id, proposal_id, row["fingerprint"], schema_digest,
                 now.isoformat(), actor),
            )
        except sqlite3.IntegrityError as exc:
            # The unique proposal_id constraint is the final replay barrier.
            raise ValueError("This approved proposal has already been reserved.") from exc
        db.execute(
            """INSERT INTO audit_events
            (event_type,actor_id,resource_type,resource_id,details_json,created_at)
            VALUES(?,?,?,?,?,?)""",
            ("mcp_tool_proposal.execution_reserved", actor, "mcp_tool_proposal",
             proposal_id, json.dumps({
                 "reservation_id": reservation_id,
                 "fingerprint": row["fingerprint"],
                 "schema_sha256": schema_digest,
                 "execution_enabled": False,
             }, sort_keys=True, separators=(",", ":")), now.isoformat()),
        )

    return {
        "reservation_id": reservation_id,
        "proposal_id": proposal_id,
        "status": "reserved",
        "reserved_at": now.isoformat(),
        "execution_enabled": False,
        "remote_call_performed": False,
    }
