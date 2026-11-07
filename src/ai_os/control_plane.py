"""Persistent catalog/control-plane registry (catalog entries are not live processes)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlsplit

from ai_os.db import connect
from ai_os.registry import list_agents


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

        CREATE TABLE IF NOT EXISTS control_plane_capabilities (
            agent_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            granted_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(agent_id, capability),
            FOREIGN KEY(agent_id) REFERENCES control_plane_agents(agent_id) ON DELETE CASCADE
        );

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
            for capability in agent.capabilities:
                db.execute(
                    """INSERT OR IGNORE INTO control_plane_capabilities
                       (agent_id, capability, granted_by, created_at)
                       VALUES (?, ?, 'profile-sync', ?)""",
                    (agent.id, capability, now),
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
    with connect() as db:
        cursor = db.execute(
            "UPDATE control_plane_agents SET enabled = ?, updated_at = ? WHERE agent_id = ?",
            (1 if enabled else 0, _now(), agent_id),
        )
        if cursor.rowcount == 0:
            return None
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
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
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
        runtime_instances = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='control_plane_runtime_instances'"
        ).fetchone()
    return {
        "agent_profiles_registered": agents,
        "logical_agents_enabled": enabled,
        "endpoints_registered": endpoints,
        "endpoints_enabled": enabled_endpoints,
        "relationships_registered": relationships,
        "runtime_instances_registered": 0 if runtime_instances is None else None,
        "runtime_status": "not_implemented_in_cp1",
        "notice": "Registered profiles and logical agents are not proof of live worker processes.",
    }
