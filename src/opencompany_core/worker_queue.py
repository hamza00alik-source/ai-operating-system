"""Durable, bounded worker queue for OpenCompany.

The queue leases already-authorized internal work only. It does not invoke
models, tools, shell commands, external integrations, or production actions.
Expired leases can be reclaimed; attempts are bounded to prevent retry loops.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4


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

    def __init__(self, database: str | Path, *, max_attempts: int = 3,
                 lease_seconds: int = 300) -> None:
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 10 and 3600")
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self._lock = RLock()
        self._db = sqlite3.connect(str(database), timeout=10,
                                   check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=10000")
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
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_worker_queue_ready "
            "ON worker_queue(state, created_at)"
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def enqueue(self, work_item_id: UUID, agent_id: UUID, payload: dict) -> None:
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
                # Reclaim expired leases, or mark them dead once retries are exhausted.
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

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute(
                "SELECT state,COUNT(*) AS total FROM worker_queue GROUP BY state"
            ).fetchall()
        return {row["state"]: int(row["total"]) for row in rows}
