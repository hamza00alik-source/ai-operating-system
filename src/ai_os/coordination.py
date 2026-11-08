"""Durable agent registry, task claiming, shared memory and audit events.

This module coordinates workers; it does not itself call an LLM or execute
external business actions. Those require separately configured adapters.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_agent(agent_id: str, name: str, role: str) -> dict:
    now = _now()
    with connect() as db:
        db.execute(
            """INSERT INTO agents (agent_id, name, role, status, last_seen)
               VALUES (?, ?, ?, 'active', ?)
               ON CONFLICT(agent_id) DO UPDATE SET
                 name=excluded.name, role=excluded.role,
                 status='active', last_seen=excluded.last_seen""",
            (agent_id, name, role, now),
        )
        db.execute(
            """INSERT INTO audit_events
               (id, event_type, actor_id, entity_type, entity_id, payload, created_at)
               VALUES (?, 'agent_registered', ?, 'agent', ?, ?, ?)""",
            (str(uuid4()), agent_id, agent_id,
             json.dumps({"name": name, "role": role}), now),
        )
        row = db.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    return dict(row)


def list_agents() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM agents ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def claim_next_task(agent_id: str) -> dict | None:
    """Atomically assign the oldest queued task to a registered active agent."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        agent = db.execute(
            "SELECT agent_id FROM agents WHERE agent_id=? AND status='active'",
            (agent_id,),
        ).fetchone()
        if agent is None:
            raise LookupError("Active agent not found")
        task = db.execute(
            "SELECT * FROM tasks WHERE status='queued' ORDER BY created_at, id LIMIT 1"
        ).fetchone()
        if task is None:
            return None
        now = _now()
        changed = db.execute(
            """UPDATE tasks SET status='running', assigned_agent=?
               WHERE id=? AND status='queued'""",
            (agent_id, task["id"]),
        ).rowcount
        if changed != 1:
            return None
        db.execute(
            """INSERT INTO audit_events
               (id, event_type, actor_id, entity_type, entity_id, payload, created_at)
               VALUES (?, 'task_claimed', ?, 'task', ?, ?, ?)""",
            (str(uuid4()), agent_id, task["id"],
             json.dumps({"previous_status": "queued", "status": "running"}), now),
        )
        updated = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
    return dict(updated)


def write_memory(key: str, content: str, source: str, created_by: str) -> dict:
    memory = {
        "id": str(uuid4()), "key": key, "content": content,
        "source": source, "created_by": created_by, "created_at": _now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO memory_entries
               (id, key, content, source, created_by, created_at)
               VALUES (:id, :key, :content, :source, :created_by, :created_at)""",
            memory,
        )
        db.execute(
            """INSERT INTO audit_events
               (id, event_type, actor_id, entity_type, entity_id, payload, created_at)
               VALUES (?, 'memory_written', ?, 'memory', ?, ?, ?)""",
            (str(uuid4()), created_by, memory["id"],
             json.dumps({"key": key, "source": source}), memory["created_at"]),
        )
    return memory


def search_memory(query: str = "", limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 100))
    with connect() as db:
        if query.strip():
            pattern = f"%{query.strip()}%"
            rows = db.execute(
                """SELECT * FROM memory_entries
                   WHERE key LIKE ? OR content LIKE ? OR source LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (pattern, pattern, pattern, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM memory_entries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def list_audit_events(limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 200))
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        result.append(item)
    return result
