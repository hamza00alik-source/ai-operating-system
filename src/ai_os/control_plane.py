"""Persistent catalog/control-plane registry (catalog entries are not live processes)."""
from __future__ import annotations

import json
import os
import hashlib
import secrets
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import urlsplit
from pathlib import Path

from ai_os.db import connect
from ai_os.registry import get_agent, list_agents


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_control_plane() -> None:
    """Create additive CP-1 tables and idempotently sync pinned profile definitions."""
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS control_plane_agents (
            agent_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT NOT NULL,
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cp_agents_department_enabled
            ON control_plane_agents(department, enabled, name);

        CREATE TABLE IF NOT EXISTS control_plane_endpoints (
            endpoint_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            protocol TEXT NOT NULL CHECK(protocol IN ('internal','mcp','a2a','openai_compatible')),
            base_url TEXT,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
            credential_ref TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS control_plane_runtime_instances (
            runtime_id TEXT PRIMARY KEY,
            runtime_name TEXT NOT NULL,
            runtime_kind TEXT NOT NULL CHECK(runtime_kind IN ('worker','agent')),
            agent_id TEXT,
            status TEXT NOT NULL CHECK(status IN ('starting','idle','working','paused','stopped','error','revoked')),
            current_job_id TEXT,
            token_hash TEXT NOT NULL,
            token_expires_at TEXT,
            registered_at TEXT NOT NULL,
            last_heartbeat_at TEXT,
            updated_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY(agent_id) REFERENCES control_plane_agents(agent_id)
        );
        CREATE INDEX IF NOT EXISTS idx_cp_runtime_heartbeat
            ON control_plane_runtime_instances(last_heartbeat_at, status);


        CREATE TABLE IF NOT EXISTS control_plane_capability_grants (
            grant_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            department_scope TEXT,
            granted_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, capability, department_scope),
            FOREIGN KEY(agent_id) REFERENCES control_plane_agents(agent_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_cp_capability_agent
            ON control_plane_capability_grants(agent_id, capability);

        CREATE TABLE IF NOT EXISTS control_plane_relationships (
            source_agent_id TEXT NOT NULL,
            target_agent_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL CHECK(relationship_type IN ('reports_to','delegates_to','collaborates_with')),
            created_at TEXT NOT NULL,
            PRIMARY KEY(source_agent_id, target_agent_id, relationship_type),
            FOREIGN KEY(source_agent_id) REFERENCES control_plane_agents(agent_id) ON DELETE CASCADE,
            FOREIGN KEY(target_agent_id) REFERENCES control_plane_agents(agent_id) ON DELETE CASCADE,
            CHECK(source_agent_id <> target_agent_id)
        );
        """)
        runtime_columns = {row[1] for row in db.execute("PRAGMA table_info(control_plane_runtime_instances)")}
        if "token_expires_at" not in runtime_columns:
            db.execute("ALTER TABLE control_plane_runtime_instances ADD COLUMN token_expires_at TEXT")
        expiry_default = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        db.execute(
            "UPDATE control_plane_runtime_instances SET token_expires_at=? WHERE token_expires_at IS NULL",
            (expiry_default,),
        )
        now = _now()
        for agent in list_agents(enabled_only=False):
            db.execute(
                """INSERT INTO control_plane_agents
                   (agent_id, profile_id, name, department, description, source,
                    capabilities_json, enabled, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     profile_id=excluded.profile_id, name=excluded.name,
                     department=excluded.department, description=excluded.description,
                     source=excluded.source, capabilities_json=excluded.capabilities_json,
                     updated_at=excluded.updated_at""",
                (agent.id, agent.id, agent.name, agent.department, agent.description,
                 agent.source, json.dumps(list(agent.capabilities)),
                 1 if agent.enabled else 0, now, now),
            )
        # Department charters explicitly authorize each named manager to delegate
        # internal tasks only within that manager's own department.
        departments_path = Path(__file__).resolve().parents[2] / "company" / "departments.json"
        try:
            department_items = json.loads(departments_path.read_text(encoding="utf-8")).get("departments", [])
        except (OSError, ValueError):
            department_items = []
        for department in department_items:
            manager_id = department.get("manager_agent_id")
            department_id = department.get("id")
            if manager_id and department_id:
                db.execute(
                    """INSERT OR IGNORE INTO control_plane_capability_grants
                       (grant_id, agent_id, capability, department_scope, granted_by, created_at)
                       VALUES (?, ?, 'task.delegate', ?, 'system:department-charter', ?)""",
                    (str(uuid4()), manager_id, department_id, now),
                )
        # The CEO is the sole company-level reporting authority.
        db.execute(
            """INSERT OR IGNORE INTO control_plane_relationships
               (source_agent_id, target_agent_id, relationship_type, created_at)
               SELECT agent_id, 'company-orchestrator', 'reports_to', ?
               FROM control_plane_agents
               WHERE agent_id <> 'company-orchestrator'""",
            (now,),
        )


def list_control_plane_agents(*, department: str | None = None,
                               enabled: bool | None = None,
                               limit: int = 500) -> list[dict]:
    clauses, values = [], []
    if department:
        clauses.append("department = ?")
        values.append(department)
    if enabled is not None:
        clauses.append("enabled = ?")
        values.append(1 if enabled else 0)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM control_plane_agents" + where +
            " ORDER BY department, name LIMIT ?", (*values, limit)
        ).fetchall()
        return [_agent_row(row) for row in rows]


def _agent_row(row) -> dict:
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    item["capabilities"] = json.loads(item.pop("capabilities_json"))
    item["metadata"] = json.loads(item.pop("metadata_json"))
    return item


def get_control_plane_agent(agent_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM control_plane_agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        item = _agent_row(row)
        item["relationships"] = [
            dict(r) for r in db.execute(
                """SELECT source_agent_id, target_agent_id, relationship_type, created_at
                   FROM control_plane_relationships
                   WHERE source_agent_id = ? OR target_agent_id = ?
                   ORDER BY relationship_type, target_agent_id""",
                (agent_id, agent_id),
            ).fetchall()
        ]
        return item


def set_agent_enabled(agent_id: str, enabled: bool) -> dict | None:
    if agent_id == "company-orchestrator" and not enabled:
        raise ValueError("The CEO agent cannot be disabled; it is the company accountability root.")
    with connect() as db:
        now = _now()
        cursor = db.execute(
            "UPDATE control_plane_agents SET enabled = ?, updated_at = ? WHERE agent_id = ?",
            (1 if enabled else 0, now, agent_id),
        )
        if cursor.rowcount == 0:
            return None
        if not enabled:
            db.execute(
                """UPDATE control_plane_runtime_instances
                   SET status='revoked', revoked_at=?, updated_at=?, current_job_id=NULL
                   WHERE agent_id=? AND revoked_at IS NULL""",
                (now, now, agent_id),
            )
    return get_control_plane_agent(agent_id)


def list_control_plane_endpoints() -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """SELECT endpoint_id, name, protocol, base_url, enabled,
                      credential_ref, metadata_json, created_at, updated_at
               FROM control_plane_endpoints ORDER BY name"""
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result


def create_control_plane_endpoint(*, name: str, protocol: str,
                                  base_url: str | None,
                                  credential_ref: str | None = None,
                                  metadata: dict | None = None) -> dict:
    """Register endpoint metadata disabled; credentials are references, never secret values."""
    if protocol not in {"internal", "mcp", "a2a", "openai_compatible"}:
        raise ValueError("Unsupported endpoint protocol")
    if protocol == "internal" and base_url:
        raise ValueError("Internal endpoints must not specify a network URL")
    if protocol != "internal" and not base_url:
        raise ValueError("Network endpoints require a base_url")
    if base_url:
        parsed = urlsplit(base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and not local_http:
            raise ValueError("Endpoint URL must use HTTPS (HTTP is allowed only for localhost)")
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ValueError("Endpoint URL must not contain credentials or a fragment")
    if credential_ref and (len(credential_ref) > 160 or any(c.isspace() for c in credential_ref)):
        raise ValueError("credential_ref must be a short secret-manager reference, not a secret")
    endpoint_id, now = str(uuid4()), _now()
    with connect() as db:
        db.execute(
            """INSERT INTO control_plane_endpoints
               (endpoint_id, name, protocol, base_url, enabled, credential_ref,
                metadata_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)""",
            (endpoint_id, name, protocol, base_url, credential_ref,
             json.dumps(metadata or {}, sort_keys=True), now, now),
        )
    return next(x for x in list_control_plane_endpoints() if x["endpoint_id"] == endpoint_id)


def control_plane_overview() -> dict:
    with connect() as db:
        agents = db.execute("SELECT COUNT(*) FROM control_plane_agents").fetchone()[0]
        enabled = db.execute("SELECT COUNT(*) FROM control_plane_agents WHERE enabled=1").fetchone()[0]
        endpoints = db.execute("SELECT COUNT(*) FROM control_plane_endpoints").fetchone()[0]
        enabled_endpoints = db.execute("SELECT COUNT(*) FROM control_plane_endpoints WHERE enabled=1").fetchone()[0]
        relationships = db.execute("SELECT COUNT(*) FROM control_plane_relationships").fetchone()[0]
        runtimes = db.execute("SELECT COUNT(*) FROM control_plane_runtime_instances").fetchone()[0]
        online_runtimes = db.execute("SELECT COUNT(*) FROM control_plane_runtime_instances WHERE revoked_at IS NULL AND status IN ('starting','idle','working','paused') AND last_heartbeat_at >= ?", ((datetime.now(timezone.utc) - timedelta(seconds=RUNTIME_HEARTBEAT_STALE_SECONDS)).isoformat(),)).fetchone()[0]
    return {
        "agent_profiles_registered": agents,
        "logical_agents_enabled": enabled,
        "endpoints_registered": endpoints,
        "endpoints_enabled": enabled_endpoints,
        "relationships_registered": relationships,
        "runtime_instances_registered": runtimes,
        "runtime_instances_healthy": online_runtimes,
        "runtime_status": "heartbeat_based",
        "notice": "Registered profiles and logical agents are not proof of live worker processes.",
    }


RUNTIME_HEARTBEAT_STALE_SECONDS = 60
RUNTIME_STATUSES = {"starting", "idle", "working", "paused", "stopped", "error"}


def _runtime_public(row, *, now: datetime | None = None) -> dict:
    item = dict(row)
    item.pop("token_hash", None)
    item["revoked"] = item.get("revoked_at") is not None
    if item["revoked"]:
        item["health"] = "revoked"
    elif not item.get("last_heartbeat_at"):
        item["health"] = "offline"
    else:
        current = now or datetime.now(timezone.utc)
        try:
            last_seen = datetime.fromisoformat(item["last_heartbeat_at"])
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age = (current - last_seen).total_seconds()
        except (TypeError, ValueError):
            age = RUNTIME_HEARTBEAT_STALE_SECONDS + 1
        item["health"] = "stale" if age > RUNTIME_HEARTBEAT_STALE_SECONDS else item["status"]
    return item


def create_runtime_instance(*, runtime_name: str, runtime_kind: str,
                            agent_id: str | None = None) -> tuple[dict, str]:
    if runtime_kind not in {"worker", "agent"}:
        raise ValueError("runtime_kind must be worker or agent")
    if runtime_kind == "agent" and not agent_id:
        raise ValueError("agent runtime requires a registered agent_id")
    if runtime_kind == "worker" and agent_id:
        raise ValueError("generic worker runtime must not claim a logical agent identity")
    runtime_id, token, now = str(uuid4()), secrets.token_urlsafe(48), _now()
    token_expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as db:
        if agent_id:
            agent = db.execute(
                "SELECT enabled FROM control_plane_agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if agent is None or not agent["enabled"]:
                raise ValueError("Only an enabled registered agent may have an agent runtime")
        db.execute(
            """INSERT INTO control_plane_runtime_instances
               (runtime_id, runtime_name, runtime_kind, agent_id, status,
                current_job_id, token_hash, token_expires_at, registered_at, last_heartbeat_at,
                updated_at, revoked_at)
               VALUES (?, ?, ?, ?, 'starting', NULL, ?, ?, ?, NULL, ?, NULL)""",
            (runtime_id, runtime_name, runtime_kind, agent_id, token_hash, token_expires_at, now, now),
        )
        row = db.execute(
            "SELECT * FROM control_plane_runtime_instances WHERE runtime_id = ?",
            (runtime_id,),
        ).fetchone()
    return _runtime_public(row), token


def list_runtime_instances(*, stale_after_seconds: int = RUNTIME_HEARTBEAT_STALE_SECONDS) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM control_plane_runtime_instances ORDER BY registered_at DESC"
        ).fetchall()
    return [_runtime_public(row) for row in rows]


def get_runtime_instance(runtime_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM control_plane_runtime_instances WHERE runtime_id = ?",
            (runtime_id,),
        ).fetchone()
    return _runtime_public(row) if row else None


def heartbeat_runtime(*, runtime_id: str, token: str, status: str,
                      current_job_id: str | None = None) -> dict:
    if status not in RUNTIME_STATUSES:
        raise ValueError("Unsupported runtime heartbeat status")
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256:
        raise PermissionError("A valid runtime credential is required")
    supplied_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = _now()
    with connect() as db:
        row = db.execute(
            "SELECT token_hash, token_expires_at, revoked_at, agent_id FROM control_plane_runtime_instances WHERE runtime_id = ?",
            (runtime_id,),
        ).fetchone()
        if row is None or row["revoked_at"] is not None or not secrets.compare_digest(
            supplied_hash, row["token_hash"]
        ):
            raise PermissionError("Runtime credential is invalid or revoked")
        if row["token_expires_at"] and datetime.fromisoformat(row["token_expires_at"]) <= datetime.now(timezone.utc):
            raise PermissionError("Runtime credential has expired; an owner must rotate it")
        if row["agent_id"]:
            agent = db.execute(
                "SELECT enabled FROM control_plane_agents WHERE agent_id=?", (row["agent_id"],)
            ).fetchone()
            if agent is None or not agent["enabled"]:
                raise PermissionError("The logical agent assigned to this runtime is disabled")
        db.execute(
            """UPDATE control_plane_runtime_instances
               SET status=?, current_job_id=?, last_heartbeat_at=?, updated_at=?
               WHERE runtime_id=? AND revoked_at IS NULL""",
            (status, current_job_id, now, now, runtime_id),
        )
        updated = db.execute(
            "SELECT * FROM control_plane_runtime_instances WHERE runtime_id = ?",
            (runtime_id,),
        ).fetchone()
    return _runtime_public(updated)


def rotate_runtime_token(runtime_id: str) -> tuple[dict, str] | None:
    token, now = secrets.token_urlsafe(48), _now()
    token_expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as db:
        row = db.execute(
            "SELECT revoked_at FROM control_plane_runtime_instances WHERE runtime_id = ?",
            (runtime_id,),
        ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        db.execute(
            "UPDATE control_plane_runtime_instances SET token_hash=?, token_expires_at=?, updated_at=? WHERE runtime_id=?",
            (token_hash, token_expires_at, now, runtime_id),
        )
        updated = db.execute(
            "SELECT * FROM control_plane_runtime_instances WHERE runtime_id = ?",
            (runtime_id,),
        ).fetchone()
    return _runtime_public(updated), token


def revoke_runtime_instance(runtime_id: str) -> dict | None:
    now = _now()
    with connect() as db:
        db.execute(
            """UPDATE control_plane_runtime_instances
               SET status='revoked', revoked_at=?, updated_at=?, current_job_id=NULL
               WHERE runtime_id=? AND revoked_at IS NULL""",
            (now, now, runtime_id),
        )
        row = db.execute(
            "SELECT * FROM control_plane_runtime_instances WHERE runtime_id = ?",
            (runtime_id,),
        ).fetchone()
    return _runtime_public(row) if row else None


def is_control_plane_agent_enabled(agent_id: str, *, fallback_enabled: bool = True) -> bool:
    """Return the authoritative CP enabled state, falling back before CP schema exists."""
    try:
        with connect() as db:
            row = db.execute(
                "SELECT enabled FROM control_plane_agents WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
    except Exception as exc:
        # Early unit tests and one-off tools may use the registry before CP startup.
        from sqlite3 import OperationalError
        if isinstance(exc, OperationalError) and "no such table" in str(exc).lower():
            return fallback_enabled
        raise
    return bool(row["enabled"]) if row is not None else False


def get_effective_agent(agent_id: str):
    """Resolve a registry profile only when both registry and CP policy enable it."""
    agent = get_agent(agent_id)
    if agent is None or not agent.enabled:
        return None
    return agent if is_control_plane_agent_enabled(agent_id, fallback_enabled=agent.enabled) else None


def list_effective_agents(*, department: str | None = None) -> list:
    """Return enabled profile objects using one CP query, not one DB query per profile."""
    agents = list_agents(enabled_only=True)
    try:
        with connect() as db:
            rows = db.execute(
                "SELECT agent_id FROM control_plane_agents WHERE enabled = 1"
            ).fetchall()
    except Exception as exc:
        from sqlite3 import OperationalError
        if isinstance(exc, OperationalError) and "no such table" in str(exc).lower():
            rows = None
        else:
            raise
    if rows is not None:
        enabled_ids = {row["agent_id"] for row in rows}
        agents = [agent for agent in agents if agent.id in enabled_ids]
    if department:
        agents = [agent for agent in agents if agent.department == department]
    return agents


def select_effective_agent(department: str):
    """Deterministically select the first enabled specialist in a department."""
    candidates = sorted(
        (agent for agent in list_effective_agents(department=department)
         if agent.id != "company-orchestrator"),
        key=lambda agent: (agent.name.casefold(), agent.id),
    )
    return candidates[0] if candidates else None


def filter_effective_agents(agents: list) -> list:
    """Filter supplied registry profiles against one authoritative CP enabled-ID query."""
    candidates = [agent for agent in agents if getattr(agent, "enabled", False)]
    try:
        with connect() as db:
            rows = db.execute(
                "SELECT agent_id FROM control_plane_agents WHERE enabled = 1"
            ).fetchall()
    except Exception as exc:
        from sqlite3 import OperationalError
        if isinstance(exc, OperationalError) and "no such table" in str(exc).lower():
            return candidates
        raise
    enabled_ids = {row["agent_id"] for row in rows}
    return [agent for agent in candidates if agent.id in enabled_ids]


BROKER_CAPABILITIES = {
    "task.delegate",
    "tool.research.read",
    "tool.knowledge.read",
    "tool.knowledge.write",
    "tool.store.read",
    "tool.store.draft",
}
_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,79}$")


def grant_capability(*, agent_id: str, capability: str,
                     department_scope: str | None, granted_by: str) -> dict:
    capability = capability.strip().lower()
    if capability not in BROKER_CAPABILITIES or not _CAPABILITY_PATTERN.fullmatch(capability):
        raise ValueError("Capability is not in the supported allowlist")
    if not is_control_plane_agent_enabled(agent_id, fallback_enabled=False):
        raise ValueError("Capability can only be granted to an enabled registered agent")
    if department_scope:
        agent = get_agent(agent_id)
        if agent is None or (agent_id != "company-orchestrator" and agent.department != department_scope):
            raise ValueError("Department-scoped capability must match the agent's department")
    grant_id, now = str(uuid4()), _now()
    with connect() as db:
        db.execute(
            """INSERT INTO control_plane_capability_grants
               (grant_id, agent_id, capability, department_scope, granted_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(agent_id, capability, department_scope) DO NOTHING""",
            (grant_id, agent_id, capability, department_scope, granted_by, now),
        )
        row = db.execute(
            """SELECT * FROM control_plane_capability_grants
               WHERE agent_id=? AND capability=? AND department_scope IS ?""",
            (agent_id, capability, department_scope),
        ).fetchone()
    return dict(row)


def list_capability_grants(*, agent_id: str | None = None) -> list[dict]:
    with connect() as db:
        if agent_id:
            rows = db.execute(
                """SELECT * FROM control_plane_capability_grants
                   WHERE agent_id=? ORDER BY capability, department_scope""", (agent_id,)
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT * FROM control_plane_capability_grants
                   ORDER BY agent_id, capability, department_scope"""
            ).fetchall()
    return [dict(row) for row in rows]


def revoke_capability_grant(grant_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM control_plane_capability_grants WHERE grant_id=?", (grant_id,)
        ).fetchone()
        if row is None:
            return None
        db.execute("DELETE FROM control_plane_capability_grants WHERE grant_id=?", (grant_id,))
    return dict(row)


def evaluate_capability(agent_id: str, capability: str,
                        department_scope: str | None = None) -> dict:
    normalized = capability.strip().lower() if isinstance(capability, str) else ""
    if normalized not in BROKER_CAPABILITIES:
        return {"allowed": False, "decision": "blocked_unknown_capability",
                "reason": "Capability is not in the supported allowlist."}
    if not is_control_plane_agent_enabled(agent_id, fallback_enabled=False):
        return {"allowed": False, "decision": "blocked_agent_disabled",
                "reason": "Agent is not enabled in the Control Plane."}
    with connect() as db:
        row = db.execute(
            """SELECT grant_id, department_scope FROM control_plane_capability_grants
               WHERE agent_id=? AND capability=?
                 AND (department_scope IS NULL OR department_scope IS ?)
               ORDER BY CASE WHEN department_scope IS NULL THEN 1 ELSE 0 END LIMIT 1""",
            (agent_id, normalized, department_scope),
        ).fetchone()
    if row is None:
        return {"allowed": False, "decision": "blocked_no_capability_grant",
                "reason": "No explicit capability grant matches this agent and scope."}
    return {"allowed": True, "decision": "allowed_explicit_grant",
            "grant_id": row["grant_id"], "department_scope": row["department_scope"],
            "reason": "An explicit owner-approved capability grant matches this request."}


def evaluate_broker_route(source_agent_id: str, target_agent_id: str) -> dict:
    source = get_effective_agent(source_agent_id)
    target = get_effective_agent(target_agent_id)
    if source is None or target is None:
        return {"allowed": False, "decision": "blocked_agent_unavailable",
                "reason": "Source and target must both be enabled registered agents."}
    if source_agent_id == target_agent_id:
        return {"allowed": False, "decision": "blocked_self_route",
                "reason": "An agent cannot delegate a task to itself."}
    if source_agent_id == "company-orchestrator":
        return {"allowed": True, "decision": "allowed_ceo_route",
                "source_agent_id": source_agent_id, "target_agent_id": target_agent_id,
                "department_scope": target.department}
    from ai_os.departments import get_department
    department = get_department(target.department)
    if department is None or department.get("manager_agent_id") != source_agent_id:
        return {"allowed": False, "decision": "blocked_department_scope",
                "reason": "Only the configured department manager may delegate to specialists in that department."}
    grant = evaluate_capability(source_agent_id, "task.delegate", target.department)
    if not grant["allowed"]:
        return {**grant, "source_agent_id": source_agent_id, "target_agent_id": target_agent_id}
    return {"allowed": True, "decision": "allowed_manager_scope",
            "source_agent_id": source_agent_id, "target_agent_id": target_agent_id,
            "department_scope": target.department, "grant_id": grant["grant_id"]}



def set_control_plane_endpoint_enabled(endpoint_id: str, enabled: bool) -> dict | None:
    """Owner-controlled MCP endpoint lifecycle; enabling does not execute a connection."""
    with connect() as db:
        row = db.execute(
            "SELECT * FROM control_plane_endpoints WHERE endpoint_id=?", (endpoint_id,)
        ).fetchone()
        if row is None:
            return None
        if enabled:
            if row["protocol"] != "mcp":
                raise ValueError("Only MCP endpoints may be enabled in CP-4; other protocols remain disabled.")
            credential_ref = row["credential_ref"]
            if credential_ref:
                if not credential_ref.startswith("env:"):
                    raise ValueError("This deployment has no secret-manager resolver; use env:NAME or omit credentials.")
                variable = credential_ref[4:]
                if not variable or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
                    raise ValueError("Credential reference must be env: followed by a valid environment variable name.")
                if not os.getenv(variable, "").strip():
                    raise ValueError("Referenced MCP credential environment variable is not configured.")
        now = _now()
        db.execute(
            "UPDATE control_plane_endpoints SET enabled=?, updated_at=? WHERE endpoint_id=?",
            (1 if enabled else 0, now, endpoint_id),
        )
        updated = db.execute(
            """SELECT endpoint_id, name, protocol, base_url, enabled,
                      credential_ref, metadata_json, created_at, updated_at
               FROM control_plane_endpoints WHERE endpoint_id=?""", (endpoint_id,)
        ).fetchone()
    item = dict(updated)
    item["enabled"] = bool(item["enabled"])
    item["metadata"] = json.loads(item.pop("metadata_json"))
    return item
