"""Durable, bounded worker queue for OpenCompany.

Owner-approved internal work is admitted atomically with its task-state change
and audit event. In composed mode, queue claims also move QUEUED tasks to
IN_PROGRESS on the same SQLite connection used by the core store.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from .domain import BUSINESS_UNIT_IDS, AgentState, AuditRecord, TaskState, WorkItem


@dataclass(frozen=True, slots=True)
class WorkerLease:
    work_item_id: UUID
    agent_id: UUID
    lease_token: UUID
    attempt: int
    expires_at: datetime
    payload: dict


class QueueError(RuntimeError):
    pass


class DurableWorkerQueue:
    """SQLite-backed queue with atomic claims and token-checked completion."""

    def __init__(
        self,
        database: str | Path | sqlite3.Connection,
        *,
        max_attempts: int = 3,
        lease_seconds: int = 300,
        lock: RLock | None = None,
    ) -> None:
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 10 and 3600")
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self._lock = lock or RLock()
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        self._db = database if isinstance(database, sqlite3.Connection) else sqlite3.connect(
            str(database), timeout=10, check_same_thread=False, isolation_level=None
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS delegation_child_tasks (
                id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS worker_queue (
                work_item_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','leased','done','dead')),
                attempts INTEGER NOT NULL DEFAULT 0,
                lease_token TEXT,
                lease_expires_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        columns = {
            row["name"] for row in self._db.execute("PRAGMA table_info(worker_queue)").fetchall()
        }
        if "cancel_requested" not in columns:
            self._db.execute(
                "ALTER TABLE worker_queue ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
            )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_queue_ready "
            "ON worker_queue(state, created_at)"
        )

    def close(self) -> None:
        if self._owns_connection:
            with self._lock:
                self._db.close()

    @staticmethod
    def _append_audit(record: AuditRecord, connection: sqlite3.Connection) -> None:
        from .persistence import _ZERO_HASH, _audit_payload, _digest, _json

        row = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = row["event_hash"] if row else _ZERO_HASH
        payload = _audit_payload(record, previous)
        connection.execute(
            """INSERT INTO audit_events
               (event_id,occurred_at,payload_json,previous_hash,event_hash)
               VALUES(?,?,?,?,?)""",
            (str(record.id), record.occurred_at.isoformat(), _json(payload),
             previous, _digest(payload)),
        )

    def enqueue_authorized(
        self, item: WorkItem, agent_id: UUID, payload: dict, record: AuditRecord
    ) -> None:
        """Atomically queue a READY task, validate its active assignee, and audit admission."""
        if item.state != TaskState.READY or item.assigned_agent_id != agent_id:
            raise QueueError("only READY work explicitly assigned to this agent can be queued")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(encoded) > 24000:
            raise ValueError("payload exceeds 24000 characters")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                task = self._db.execute(
                    "SELECT state,assigned_agent_id,department,dependencies_json,business_id FROM work_items WHERE id=?",
                    (str(item.id),),
                ).fetchone()
                agent = self._db.execute(
                    "SELECT state,department,role_key,team_key FROM agent_profiles WHERE id=?",
                    (str(agent_id),),
                ).fetchone()
                if (
                    task is None or task["state"] != TaskState.READY.value
                    or task["assigned_agent_id"] != str(agent_id)
                ):
                    raise QueueError("work item changed or is not READY for this assignee")
                if (
                    agent is None or agent["state"] != AgentState.ACTIVE.value
                    or agent["department"] != task["department"]
                ):
                    raise QueueError("assignee must be an active profile in the work item's department")
                dependencies = json.loads(task["dependencies_json"])
                for dependency_id in dependencies:
                    dependency = self._db.execute(
                        "SELECT state,business_id FROM work_items WHERE id=?", (dependency_id,)
                    ).fetchone()
                    if dependency is None or dependency["state"] != TaskState.COMPLETED.value:
                        raise QueueError("all prerequisite work items must be completed before queue admission")
                    if dependency["business_id"] != task["business_id"]:
                        raise QueueError("work item dependencies cannot cross business-unit boundaries")
                child = self._db.execute(
                    "SELECT state,assigned_agent_id,role_key,team_key "
                    "FROM delegation_child_tasks WHERE id=?",
                    (str(item.id),),
                ).fetchone()
                if child is not None:
                    if (
                        child["state"] not in {"approved", "queued"}
                        or child["assigned_agent_id"] != str(agent_id)
                        or child["role_key"] != agent["role_key"]
                        or child["team_key"] != agent["team_key"]
                    ):
                        raise QueueError("delegated task is not approved for re-admission or its assignee identity changed")
                    self._db.execute(
                        "UPDATE delegation_child_tasks SET state='queued' "
                        "WHERE id=? AND state IN ('approved','queued')",
                        (str(item.id),),
                    )
                # A work item has one durable queue row for its whole lifecycle.
                # Allow an owner-reviewed retry/revision to reuse a terminal row,
                # but never overwrite queued or actively leased work.
                cursor = self._db.execute(
                    """INSERT INTO worker_queue
                       (work_item_id,agent_id,payload_json,state,attempts,lease_token,
                        lease_expires_at,last_error,created_at,updated_at)
                       VALUES(?,?,?,'queued',0,NULL,NULL,NULL,?,?)
                       ON CONFLICT(work_item_id) DO UPDATE SET
                         agent_id=excluded.agent_id,
                         payload_json=excluded.payload_json,
                         state='queued',
                         attempts=0,
                         lease_token=NULL,
                         lease_expires_at=NULL,
                         last_error=NULL,
                         created_at=excluded.created_at,
                         updated_at=excluded.updated_at
                       WHERE worker_queue.state IN ('dead','done')""",
                    (str(item.id), str(agent_id), encoded, now, now),
                )
                if cursor.rowcount != 1:
                    raise QueueError("work item already has queued or actively leased work")
                cursor = self._db.execute(
                    "UPDATE work_items SET state=? WHERE id=? AND state=?",
                    (TaskState.QUEUED.value, str(item.id), TaskState.READY.value),
                )
                if cursor.rowcount != 1:
                    raise QueueError("work item changed before queue admission")
                self._append_audit(record, self._db)
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def enqueue(self, work_item_id: UUID, agent_id: UUID, payload: dict) -> None:
        """Low-level queue insert retained for isolated queue tests and maintenance."""
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(encoded) > 24000:
            raise ValueError("payload exceeds 24000 characters")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                self._db.execute(
                    """INSERT INTO worker_queue
                    (work_item_id,agent_id,payload_json,state,created_at,updated_at)
                    VALUES(?,?,?,'queued',?,?)""",
                    (str(work_item_id), str(agent_id), encoded, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise QueueError("work item is already present in the worker queue") from exc

    def claim(self, agent_id: UUID, *, now: datetime | None = None) -> WorkerLease | None:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            raise ValueError("now must be timezone-aware UTC")
        expires = instant + timedelta(seconds=self.lease_seconds)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                expired_cancelled = self._db.execute(
                    "SELECT work_item_id,agent_id FROM worker_queue "
                    "WHERE state='leased' AND cancel_requested=1 AND lease_expires_at<=?",
                    (instant.isoformat(),),
                ).fetchall()
                for cancelled in expired_cancelled:
                    self._db.execute(
                        "UPDATE work_items SET state=? WHERE id=? AND state IN (?,?)",
                        (TaskState.CANCELLED.value, cancelled["work_item_id"],
                         TaskState.QUEUED.value, TaskState.IN_PROGRESS.value),
                    )
                    self._db.execute(
                        """UPDATE worker_queue SET state='dead',lease_token=NULL,
                           lease_expires_at=NULL,last_error='owner_cancelled',updated_at=?
                           WHERE work_item_id=? AND state='leased' AND cancel_requested=1""",
                        (instant.isoformat(), cancelled["work_item_id"]),
                    )
                    self._append_audit(AuditRecord(
                        id=uuid4(), occurred_at=instant, actor_type="worker",
                        actor_id=cancelled["agent_id"], action="worker.cancellation_recovered",
                        subject_type="work_item", subject_id=cancelled["work_item_id"],
                        outcome="recorded", correlation_id=str(uuid4()),
                        details={"reason": "owner_cancelled_after_worker_interruption"},
                    ), self._db)
                expired_dead = self._db.execute(
                    "SELECT work_item_id,agent_id FROM worker_queue "
                    "WHERE state='leased' AND lease_expires_at<=? AND attempts>=?",
                    (instant.isoformat(), self.max_attempts),
                ).fetchall()
                for expired in expired_dead:
                    cursor = self._db.execute(
                        "UPDATE work_items SET state=? WHERE id=? AND state=?",
                        (TaskState.FAILED.value, expired["work_item_id"], TaskState.IN_PROGRESS.value),
                    )
                    if cursor.rowcount == 1:
                        self._append_audit(AuditRecord(
                            id=uuid4(), occurred_at=instant, actor_type="worker",
                            actor_id=expired["agent_id"], action="worker.lease_dead_lettered",
                            subject_type="work_item", subject_id=expired["work_item_id"],
                            outcome="failed", correlation_id=str(uuid4()),
                            details={"reason": "lease_expired_retry_limit"},
                        ), self._db)
                self._db.execute(
                    """UPDATE worker_queue SET
                       state=CASE WHEN attempts>=? THEN 'dead' ELSE 'queued' END,
                       lease_token=NULL, lease_expires_at=NULL,
                       last_error=CASE WHEN attempts>=? THEN 'lease_expired_retry_limit' ELSE last_error END,
                       updated_at=?
                       WHERE state='leased' AND lease_expires_at<=?""",
                    (self.max_attempts, self.max_attempts, instant.isoformat(), instant.isoformat()),
                )
                row = self._db.execute(
                    """SELECT * FROM worker_queue WHERE state='queued' AND agent_id=?
                       AND attempts<? ORDER BY created_at,work_item_id LIMIT 1""",
                    (str(agent_id), self.max_attempts),
                ).fetchone()
                if row is None:
                    self._db.execute("COMMIT")
                    return None
                if not self._owns_connection:
                    task = self._db.execute(
                        "SELECT state,assigned_agent_id FROM work_items WHERE id=?",
                        (row["work_item_id"],),
                    ).fetchone()
                    if (
                        task is None or task["assigned_agent_id"] != str(agent_id)
                        or task["state"] not in {TaskState.QUEUED.value, TaskState.IN_PROGRESS.value}
                    ):
                        raise QueueError("queued work item is missing, reassigned, or in an invalid state")
                    if task["state"] == TaskState.QUEUED.value:
                        self._db.execute(
                            "UPDATE work_items SET state=? WHERE id=? AND state=?",
                            (TaskState.IN_PROGRESS.value, row["work_item_id"], TaskState.QUEUED.value),
                        )
                        event = AuditRecord(
                            id=uuid4(), occurred_at=instant, actor_type="worker",
                            actor_id=str(agent_id), action="worker.task_claimed",
                            subject_type="work_item", subject_id=row["work_item_id"],
                            outcome="recorded", correlation_id=str(uuid4()),
                            details={"attempt": int(row["attempts"]) + 1},
                        )
                        self._append_audit(event, self._db)
                token = uuid4()
                attempt = int(row["attempts"]) + 1
                self._db.execute(
                    """UPDATE worker_queue SET state='leased',attempts=?,lease_token=?,
                       lease_expires_at=?,updated_at=? WHERE work_item_id=? AND state='queued'""",
                    (attempt, str(token), expires.isoformat(), instant.isoformat(), row["work_item_id"]),
                )
                self._db.execute("COMMIT")
                return WorkerLease(
                    work_item_id=UUID(row["work_item_id"]), agent_id=UUID(row["agent_id"]),
                    lease_token=token, attempt=attempt, expires_at=expires,
                    payload=json.loads(row["payload_json"]),
                )
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def renew(self, lease: WorkerLease, *, now: datetime | None = None) -> bool:
        """Extend a live lease only while its exact token still owns the task."""
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            raise ValueError("now must be timezone-aware UTC")
        expires = instant + timedelta(seconds=self.lease_seconds)
        with self._lock:
            cursor = self._db.execute(
                """UPDATE worker_queue SET lease_expires_at=?,updated_at=?
                   WHERE work_item_id=? AND agent_id=? AND state='leased'
                     AND lease_token=? AND lease_expires_at>?""",
                (expires.isoformat(), instant.isoformat(), str(lease.work_item_id),
                 str(lease.agent_id), str(lease.lease_token), instant.isoformat()),
            )
            return cursor.rowcount == 1


    def request_cancel(self, work_item_id: UUID, record: AuditRecord) -> str:
        """Record an owner cancellation; queued work is cancelled immediately, leased work cooperatively."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT state,cancel_requested FROM worker_queue WHERE work_item_id=?",
                    (str(work_item_id),),
                ).fetchone()
                if row is None:
                    raise QueueError("work item has no queue entry")
                if row["state"] in {"done", "dead"}:
                    if row["state"] == "dead" and row["cancel_requested"]:
                        self._db.execute("COMMIT")
                        return "cancelled"
                    raise QueueError("terminal queue work cannot be cancelled")
                if row["cancel_requested"]:
                    self._db.execute("COMMIT")
                    return "cancellation_requested" if row["state"] == "leased" else "cancelled"
                if row["state"] == "queued":
                    cursor = self._db.execute(
                        "UPDATE work_items SET state=? WHERE id=? AND state=?",
                        (TaskState.CANCELLED.value, str(work_item_id), TaskState.QUEUED.value),
                    )
                    if cursor.rowcount != 1:
                        raise QueueError("work item is no longer queued")
                    self._db.execute(
                        """UPDATE worker_queue SET state='dead',cancel_requested=1,
                           last_error='owner_cancelled',updated_at=?
                           WHERE work_item_id=? AND state='queued'""",
                        (now, str(work_item_id)),
                    )
                    result = "cancelled"
                else:
                    self._db.execute(
                        "UPDATE worker_queue SET cancel_requested=1,updated_at=? "
                        "WHERE work_item_id=? AND state='leased'",
                        (now, str(work_item_id)),
                    )
                    result = "cancellation_requested"
                self._append_audit(record, self._db)
                self._db.execute("COMMIT")
                return result
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def is_cancel_requested(self, lease: WorkerLease) -> bool:
        with self._lock:
            row = self._db.execute(
                """SELECT 1 FROM worker_queue WHERE work_item_id=? AND agent_id=?
                   AND state='leased' AND lease_token=? AND cancel_requested=1""",
                (str(lease.work_item_id), str(lease.agent_id), str(lease.lease_token)),
            ).fetchone()
        return row is not None

    def finalize_cancel(self, lease: WorkerLease, record: AuditRecord) -> bool:
        """Commit a requested cancellation only for the worker holding the live token."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    """SELECT 1 FROM worker_queue WHERE work_item_id=? AND agent_id=?
                       AND state='leased' AND lease_token=? AND cancel_requested=1
                       AND lease_expires_at>?""",
                    (str(lease.work_item_id), str(lease.agent_id),
                     str(lease.lease_token), now),
                ).fetchone()
                if row is None:
                    self._db.execute("ROLLBACK")
                    return False
                cursor = self._db.execute(
                    "UPDATE work_items SET state=? WHERE id=? AND state=?",
                    (TaskState.CANCELLED.value, str(lease.work_item_id), TaskState.IN_PROGRESS.value),
                )
                if cursor.rowcount != 1:
                    raise QueueError("work item is no longer in progress for cancellation")
                cursor = self._db.execute(
                    """UPDATE worker_queue SET state='dead',lease_token=NULL,
                       lease_expires_at=NULL,last_error='owner_cancelled',updated_at=?
                       WHERE work_item_id=? AND agent_id=? AND state='leased'
                         AND lease_token=? AND cancel_requested=1""",
                    (now, str(lease.work_item_id), str(lease.agent_id), str(lease.lease_token)),
                )
                if cursor.rowcount != 1:
                    raise QueueError("worker lease changed during cancellation")
                self._append_audit(record, self._db)
                self._db.execute("COMMIT")
                return True
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def complete(self, lease: WorkerLease) -> None:
        self._finish(lease, "done", None)

    def fail(self, lease: WorkerLease, error_code: str) -> str:
        if not error_code or len(error_code) > 120:
            raise ValueError("error_code must contain 1-120 characters")
        with self._lock:
            row = self._db.execute(
                "SELECT attempts FROM worker_queue WHERE work_item_id=? AND state='leased' AND lease_token=?",
                (str(lease.work_item_id), str(lease.lease_token)),
            ).fetchone()
            if row is None:
                raise QueueError("lease is stale or no longer owned by this worker")
            state = "dead" if int(row["attempts"]) >= self.max_attempts else "queued"
            self._finish(lease, state, error_code)
            return state

    def _finish(self, lease: WorkerLease, state: str, error: str | None) -> None:
        with self._lock:
            cursor = self._db.execute(
                """UPDATE worker_queue SET state=?,lease_token=NULL,lease_expires_at=NULL,
                   last_error=?,updated_at=? WHERE work_item_id=? AND state='leased' AND lease_token=?""",
                (state, error, datetime.now(timezone.utc).isoformat(),
                 str(lease.work_item_id), str(lease.lease_token)),
            )
            if cursor.rowcount != 1:
                raise QueueError("lease is stale or no longer owned by this worker")

    def available_agent_ids(self, *, now: datetime | None = None) -> tuple[UUID, ...]:
        """Return only agents with queued work or an expired lease to recover."""
        instant = now or datetime.now(timezone.utc)
        with self._lock:
            rows = self._db.execute(
                """SELECT DISTINCT agent_id FROM worker_queue
                   WHERE state='queued' OR (state='leased' AND lease_expires_at<=?)
                   ORDER BY agent_id""",
                (instant.isoformat(),),
            ).fetchall()
        return tuple(UUID(row["agent_id"]) for row in rows)

    def get_entry(self, work_item_id: UUID) -> dict | None:
        """Return secret-free queue lifecycle metadata for one work item."""
        with self._lock:
            row = self._db.execute(
                """SELECT work_item_id,agent_id,state,attempts,lease_expires_at,
                          last_error,created_at,updated_at
                   FROM worker_queue WHERE work_item_id=?""",
                (str(work_item_id),),
            ).fetchone()
        return dict(row) if row is not None else None

    def counts(self, business_id: str | None = None) -> dict[str, int]:
        if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
            raise ValueError("unknown business unit for worker queue counts")
        with self._lock:
            if business_id is None:
                rows = self._db.execute(
                    "SELECT state,COUNT(*) AS total FROM worker_queue GROUP BY state"
                ).fetchall()
            else:
                rows = self._db.execute(
                    """SELECT q.state,COUNT(*) AS total FROM worker_queue q
                       JOIN work_items w ON w.id=q.work_item_id
                       WHERE w.business_id=? GROUP BY q.state""",
                    (business_id,),
                ).fetchall()
        return {row["state"]: int(row["total"]) for row in rows}
