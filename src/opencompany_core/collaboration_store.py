"""Durable, audited agent-to-agent handoff records."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID

from .collaboration import (
    AgentHandoff, HandoffState, accept_handoff, decline_handoff, deliver_handoff,
)
from .domain import AgentState, AuditRecord, TaskState
from .persistence import _ZERO_HASH, _audit_payload, _digest, _json


class HandoffRepository:
    """Persist peer handoffs on the core SQLite connection and audit chain."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db = connection
        self._lock = lock
        with self._lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS agent_handoffs (
                    id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL REFERENCES work_items(id),
                    sender_agent_id TEXT NOT NULL REFERENCES agent_profiles(id),
                    recipient_agent_id TEXT NOT NULL REFERENCES agent_profiles(id),
                    purpose TEXT NOT NULL,
                    requested_result TEXT NOT NULL,
                    context TEXT NOT NULL,
                    artifact_ids_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    response_artifact_ids_json TEXT NOT NULL
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_handoffs_work_item ON agent_handoffs(work_item_id,created_at)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_handoffs_recipient ON agent_handoffs(recipient_agent_id,state,created_at)"
            )

    @staticmethod
    def _audit(record: AuditRecord, db: sqlite3.Connection) -> None:
        row = db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = row["event_hash"] if row else _ZERO_HASH
        payload = _audit_payload(record, previous)
        db.execute(
            "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
            (str(record.id), record.occurred_at.isoformat(), _json(payload), previous, _digest(payload)),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AgentHandoff:
        return AgentHandoff(
            id=UUID(row["id"]), work_item_id=UUID(row["work_item_id"]),
            sender_agent_id=UUID(row["sender_agent_id"]),
            recipient_agent_id=UUID(row["recipient_agent_id"]),
            purpose=row["purpose"], requested_result=row["requested_result"],
            context=row["context"], artifact_ids=tuple(UUID(v) for v in json.loads(row["artifact_ids_json"])),
            state=HandoffState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            response_artifact_ids=tuple(UUID(v) for v in json.loads(row["response_artifact_ids_json"])),
        )

    def create(self, handoff: AgentHandoff, record: AuditRecord) -> AgentHandoff:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                task = self._db.execute(
                    "SELECT state,assigned_agent_id,department FROM work_items WHERE id=?",
                    (str(handoff.work_item_id),),
                ).fetchone()
                sender = self._db.execute(
                    "SELECT state,department FROM agent_profiles WHERE id=?",
                    (str(handoff.sender_agent_id),),
                ).fetchone()
                recipient = self._db.execute(
                    "SELECT state,department FROM agent_profiles WHERE id=?",
                    (str(handoff.recipient_agent_id),),
                ).fetchone()
                if task is None or task["state"] != TaskState.IN_PROGRESS.value:
                    raise ValueError("handoffs require an in-progress work item")
                if task["assigned_agent_id"] != str(handoff.sender_agent_id):
                    raise ValueError("handoff sender must own the in-progress work item")
                if sender is None or sender["state"] != AgentState.ACTIVE.value:
                    raise ValueError("handoff sender must be active")
                if recipient is None or recipient["state"] != AgentState.ACTIVE.value:
                    raise ValueError("handoff recipient must be active")
                if recipient["department"] != task["department"]:
                    raise ValueError("handoff recipient must belong to the work item's department")
                for artifact_id in handoff.artifact_ids:
                    artifact = self._db.execute(
                        "SELECT work_item_id FROM deliverables WHERE id=?", (str(artifact_id),)
                    ).fetchone()
                    if artifact is None or artifact["work_item_id"] != str(handoff.work_item_id):
                        raise ValueError("handoff may reference only artifacts attached to its work item")
                self._db.execute(
                    """INSERT INTO agent_handoffs
                       (id,work_item_id,sender_agent_id,recipient_agent_id,purpose,requested_result,
                        context,artifact_ids_json,state,created_at,updated_at,response_artifact_ids_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(handoff.id), str(handoff.work_item_id), str(handoff.sender_agent_id),
                     str(handoff.recipient_agent_id), handoff.purpose, handoff.requested_result,
                     handoff.context, _json([str(v) for v in handoff.artifact_ids]),
                     handoff.state.value, handoff.created_at.isoformat(),
                     handoff.updated_at.isoformat(), _json([])),
                )
                self._audit(record, self._db)
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        return handoff

    def get(self, handoff_id: UUID) -> AgentHandoff | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM agent_handoffs WHERE id=?", (str(handoff_id),)).fetchone()
        return self._from_row(row) if row else None

    def list_for_work_item(self, work_item_id: UUID) -> tuple[AgentHandoff, ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM agent_handoffs WHERE work_item_id=? ORDER BY created_at,id",
                (str(work_item_id),),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def transition(self, updated: AgentHandoff, expected: HandoffState, record: AuditRecord) -> bool:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if updated.state == HandoffState.DELIVERED:
                    for artifact_id in updated.response_artifact_ids:
                        artifact = self._db.execute(
                            "SELECT work_item_id FROM deliverables WHERE id=?", (str(artifact_id),)
                        ).fetchone()
                        if artifact is None or artifact["work_item_id"] != str(updated.work_item_id):
                            raise ValueError("handoff response artifacts must belong to its work item")
                cursor = self._db.execute(
                    """UPDATE agent_handoffs SET state=?,updated_at=?,response_artifact_ids_json=?
                       WHERE id=? AND state=?""",
                    (updated.state.value, updated.updated_at.isoformat(),
                     _json([str(v) for v in updated.response_artifact_ids]),
                     str(updated.id), expected.value),
                )
                if cursor.rowcount != 1:
                    self._db.execute("ROLLBACK")
                    return False
                self._audit(record, self._db)
                self._db.execute("COMMIT")
                return True
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
