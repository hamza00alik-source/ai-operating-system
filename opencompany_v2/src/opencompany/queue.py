"""Durable execution queue with leases, retries, and idempotent enqueueing."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.isoformat()


class ExecutionQueue:
    """SQLite-backed queue. A claimed job is protected by a renewable lease.

    Handlers must be idempotent: a worker can crash after performing an action
    but before acknowledging it, so an expired lease can cause redelivery.
    """
    def __init__(self, db: sqlite3.Connection, lock: RLock | None = None):
        self.db = db
        self.lock = lock or RLock()
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS execution_jobs(
              id TEXT PRIMARY KEY, task_id TEXT NOT NULL, payload TEXT NOT NULL,
              state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL, available_at TEXT NOT NULL,
              lease_owner TEXT, lease_until TEXT, result TEXT, last_error TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(task_id)
            );
            CREATE INDEX IF NOT EXISTS idx_execution_jobs_ready
              ON execution_jobs(state, available_at, created_at);
            """)
            self.db.commit()

    def enqueue(self, task_id: str, payload: dict, max_attempts: int = 3) -> str:
        if not task_id or max_attempts < 1:
            raise ValueError("task_id and positive max_attempts are required")
        now = _stamp(_now())
        with self.lock:
            existing = self.db.execute(
                "SELECT id FROM execution_jobs WHERE task_id=?", (str(task_id),)
            ).fetchone()
            if existing:
                return existing["id"] if isinstance(existing, sqlite3.Row) else existing[0]
            job_id = str(uuid4())
            self.db.execute("""INSERT INTO execution_jobs
                (id,task_id,payload,state,max_attempts,available_at,created_at,updated_at)
                VALUES(?,?,?,'queued',?,?,?,?)""",
                (job_id, str(task_id), json.dumps(payload, sort_keys=True),
                 max_attempts, now, now, now))
            self.db.commit()
            return job_id

    def claim(self, worker_id: str, lease_seconds: int = 60):
        if not worker_id or lease_seconds < 1:
            raise ValueError("worker_id and positive lease_seconds are required")
        now_dt = _now()
        now = _stamp(now_dt)
        lease_until = _stamp(now_dt + timedelta(seconds=lease_seconds))
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                # Expired leases are requeued unless the attempt budget is spent.
                self.db.execute("""UPDATE execution_jobs SET
                    state=CASE WHEN attempts>=max_attempts THEN 'dead' ELSE 'queued' END,
                    lease_owner=NULL, lease_until=NULL, updated_at=?
                    WHERE state='leased' AND lease_until<=?""", (now, now))
                row = self.db.execute("""SELECT id FROM execution_jobs
                    WHERE state='queued' AND available_at<=?
                    ORDER BY created_at,id LIMIT 1""", (now,)).fetchone()
                if row is None:
                    self.db.commit()
                    return None
                job_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
                self.db.execute("""UPDATE execution_jobs SET state='leased',
                    lease_owner=?,lease_until=?,attempts=attempts+1,updated_at=?
                    WHERE id=? AND state='queued'""",
                    (worker_id, lease_until, now, job_id))
                claimed = self.db.execute("SELECT * FROM execution_jobs WHERE id=?", (job_id,)).fetchone()
                self.db.commit()
                return dict(claimed)
            except Exception:
                self.db.rollback()
                raise

    def heartbeat(self, job_id: str, worker_id: str, lease_seconds: int = 60) -> bool:
        now_dt = _now()
        with self.lock:
            cur = self.db.execute("""UPDATE execution_jobs SET lease_until=?,updated_at=?
                WHERE id=? AND state='leased' AND lease_owner=? AND lease_until>?""",
                (_stamp(now_dt + timedelta(seconds=lease_seconds)), _stamp(now_dt),
                 job_id, worker_id, _stamp(now_dt)))
            self.db.commit()
            return cur.rowcount == 1

    def complete(self, job_id: str, worker_id: str, result: dict) -> bool:
        with self.lock:
            cur = self.db.execute("""UPDATE execution_jobs SET state='completed',
                result=?,lease_owner=NULL,lease_until=NULL,updated_at=?
                WHERE id=? AND state='leased' AND lease_owner=?""",
                (json.dumps(result, sort_keys=True), _stamp(_now()), job_id, worker_id))
            self.db.commit()
            return cur.rowcount == 1

    def fail(self, job_id: str, worker_id: str, error: str, retry_delay_seconds: int = 0) -> bool:
        if retry_delay_seconds < 0:
            raise ValueError("retry delay cannot be negative")
        now_dt = _now()
        with self.lock:
            row = self.db.execute("""SELECT attempts,max_attempts FROM execution_jobs
                WHERE id=? AND state='leased' AND lease_owner=?""", (job_id, worker_id)).fetchone()
            if row is None:
                return False
            exhausted = row["attempts"] >= row["max_attempts"]
            state = "dead" if exhausted else "queued"
            available = _stamp(now_dt + timedelta(seconds=retry_delay_seconds))
            cur = self.db.execute("""UPDATE execution_jobs SET state=?,available_at=?,
                last_error=?,lease_owner=NULL,lease_until=NULL,updated_at=?
                WHERE id=? AND state='leased' AND lease_owner=?""",
                (state, available, str(error)[:2000], _stamp(now_dt), job_id, worker_id))
            self.db.commit()
            return cur.rowcount == 1

    def get(self, job_id: str):
        with self.lock:
            row = self.db.execute("SELECT * FROM execution_jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list(self, state: str | None = None):
        with self.lock:
            if state:
                rows = self.db.execute("SELECT * FROM execution_jobs WHERE state=? ORDER BY created_at", (state,))
            else:
                rows = self.db.execute("SELECT * FROM execution_jobs ORDER BY created_at")
            return [dict(row) for row in rows]
