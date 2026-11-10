"""Durable, owner-reviewable manager delegation proposals.

Proposals and child task drafts are persisted separately from execution queues.
Creating a proposal never activates profiles, changes parent task state, or
enqueues work.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4


class DelegationRepository:
    def __init__(
        self, database: str | Path | sqlite3.Connection, lock: RLock | None = None
    ) -> None:
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        if self._owns_connection:
            self.database = str(database)
            if self.database != ":memory:":
                parent = Path(self.database).expanduser().resolve().parent
                if not parent.exists():
                    raise FileNotFoundError(f"database directory does not exist: {parent}")
            self._lock = lock or RLock()
            self._db = sqlite3.connect(
                self.database, timeout=10, check_same_thread=False, isolation_level=None
            )
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.execute("PRAGMA busy_timeout = 10000")
        else:
            self.database = "<shared-connection>"
            self._db = database
            self._lock = lock or RLock()
            self._db.row_factory = sqlite3.Row
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS delegation_proposals (
                id TEXT PRIMARY KEY,
                parent_work_item_id TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                manager_agent_id TEXT,
                mode TEXT NOT NULL,
                team_key TEXT,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(parent_work_item_id, request_hash)
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS delegation_child_tasks (
                id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL REFERENCES delegation_proposals(id),
                parent_work_item_id TEXT NOT NULL,
                assigned_agent_id TEXT NOT NULL,
                role_key TEXT NOT NULL,
                team_key TEXT NOT NULL,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_delegation_children_parent
            ON delegation_child_tasks(parent_work_item_id, created_at)
        """)

    def close(self) -> None:
        if self._owns_connection:
            with self._lock:
                self._db.close()

    def create_proposal(
        self, *, parent_work_item_id: UUID, request: dict, manager_agent_id: UUID | None,
        mode: str, team_key: str | None, children: list[dict],
    ) -> dict:
        canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        proposal_id = str(uuid4())
        payload = {
            "request": request,
            "manager_agent_id": str(manager_agent_id) if manager_agent_id else None,
            "mode": mode,
            "team_key": team_key,
        }
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                existing = self._db.execute(
                    "SELECT id FROM delegation_proposals WHERE parent_work_item_id=? AND request_hash=?",
                    (str(parent_work_item_id), request_hash),
                ).fetchone()
                if existing:
                    self._db.execute("COMMIT")
                    return self.get_proposal(UUID(existing["id"]))
                self._db.execute(
                    """INSERT INTO delegation_proposals
                       (id,parent_work_item_id,request_hash,manager_agent_id,mode,team_key,
                        status,payload_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (proposal_id, str(parent_work_item_id), request_hash,
                     payload["manager_agent_id"], mode, team_key, "draft",
                     json.dumps(payload, sort_keys=True), now),
                )
                for child in children:
                    self._db.execute(
                        """INSERT INTO delegation_child_tasks
                           (id,proposal_id,parent_work_item_id,assigned_agent_id,role_key,
                            team_key,title,objective,state,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (str(uuid4()), proposal_id, str(parent_work_item_id),
                         child["assigned_agent_id"], child["role_key"], child["team_key"],
                         child["title"], child["objective"], "draft", now),
                    )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return self.get_proposal(UUID(proposal_id))

    def get_proposal(self, proposal_id: UUID) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM delegation_proposals WHERE id=?", (str(proposal_id),)
            ).fetchone()
            if row is None:
                return None
            children = self._db.execute(
                """SELECT id,assigned_agent_id,role_key,team_key,title,objective,state,created_at
                   FROM delegation_child_tasks WHERE proposal_id=? ORDER BY role_key,id""",
                (str(proposal_id),),
            ).fetchall()
        return {
            "id": row["id"], "parent_work_item_id": row["parent_work_item_id"],
            "manager_agent_id": row["manager_agent_id"], "mode": row["mode"],
            "team_key": row["team_key"], "status": row["status"],
            "payload": json.loads(row["payload_json"]), "created_at": row["created_at"],
            "children": [dict(child) for child in children],
            "execution_started": False, "queue_entries_created": False,
        }

    def list_for_parent(self, parent_work_item_id: UUID) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id FROM delegation_proposals WHERE parent_work_item_id=? ORDER BY created_at,id",
                (str(parent_work_item_id),),
            ).fetchall()
        return [self.get_proposal(UUID(row["id"])) for row in rows]
