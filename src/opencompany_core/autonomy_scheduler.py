"""Restart-safe, zero-dependency scheduler for bounded internal automations.

Jobs and individual execution attempts are persisted in the company SQLite
store. A due job is claimed with a lease before execution; expired leases make
interrupted work eligible again after a process restart. Callbacks must be
idempotent because a process can stop after its side effect but before
recording completion.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class DurableAutomationScheduler:
    """Run registered internal jobs when their persisted due time arrives."""

    def __init__(
        self,
        database: sqlite3.Connection,
        *,
        lock: RLock | None = None,
        lease_seconds: int = 300,
        max_backoff_seconds: int = 900,
    ) -> None:
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 10 and 3600")
        if not 10 <= max_backoff_seconds <= 86400:
            raise ValueError("max_backoff_seconds must be between 10 and 86400")
        self._db = database
        self._db.row_factory = sqlite3.Row
        self._lock = lock or RLock()
        self.lease_seconds = lease_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._callbacks: dict[str, object] = {}
        with self._lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS automation_jobs (
                    job_id TEXT PRIMARY KEY,
                    interval_seconds INTEGER NOT NULL CHECK(interval_seconds BETWEEN 1 AND 86400),
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                    next_run_at TEXT NOT NULL,
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    last_started_at TEXT,
                    last_finished_at TEXT,
                    last_status TEXT NOT NULL DEFAULT 'scheduled'
                        CHECK(last_status IN ('scheduled','running','succeeded','failed')),
                    last_error_code TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS automation_job_runs (
                    run_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    lease_token TEXT NOT NULL UNIQUE,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL
                        CHECK(status IN ('running','succeeded','failed','interrupted')),
                    error_code TEXT,
                    FOREIGN KEY(job_id) REFERENCES automation_jobs(job_id)
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_automation_jobs_due "
                "ON automation_jobs(enabled,next_run_at,lease_expires_at)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_automation_job_runs_job "
                "ON automation_job_runs(job_id,started_at DESC)"
            )

    def register_interval_job(
        self, job_id: str, interval_seconds: int, callback, *, enabled: bool = True
    ) -> None:
        """Register a bounded callback without resetting an existing due time."""
        if not job_id or len(job_id) > 120:
            raise ValueError("job_id must contain 1-120 characters")
        if not 1 <= interval_seconds <= 86400:
            raise ValueError("interval_seconds must be between 1 and 86400")
        if not callable(callback):
            raise ValueError("callback must be callable")
        now = _stamp(_now())
        with self._lock:
            self._db.execute(
                """INSERT INTO automation_jobs
                   (job_id,interval_seconds,enabled,next_run_at,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     interval_seconds=excluded.interval_seconds,
                     enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (job_id, interval_seconds, int(enabled), now, now),
            )
            self._callbacks[job_id] = callback

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "UPDATE automation_jobs SET enabled=?,updated_at=? WHERE job_id=?",
                (int(bool(enabled)), _stamp(_now()), job_id),
            )
            return cursor.rowcount == 1

    def run_due(self, *, limit: int = 10) -> dict[str, int]:
        """Claim and run due jobs; expired leases recover interrupted executions."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        stats = {"claimed": 0, "succeeded": 0, "failed": 0, "unregistered": 0}
        now = _now()
        now_text = _stamp(now)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                rows = self._db.execute(
                    """SELECT job_id,lease_token FROM automation_jobs
                       WHERE enabled=1 AND next_run_at<=?
                         AND (lease_token IS NULL OR lease_expires_at<=?)
                       ORDER BY next_run_at,job_id LIMIT ?""",
                    (now_text, now_text, limit),
                ).fetchall()
                claims = []
                for row in rows:
                    job_id = row["job_id"]
                    previous_token = row["lease_token"]
                    if previous_token:
                        self._db.execute(
                            """UPDATE automation_job_runs
                               SET status='interrupted',finished_at=?,
                                   error_code='lease_expired'
                               WHERE lease_token=? AND status='running'""",
                            (now_text, previous_token),
                        )
                    token = str(uuid4())
                    run_id = str(uuid4())
                    expires = _stamp(now + timedelta(seconds=self.lease_seconds))
                    cursor = self._db.execute(
                        """UPDATE automation_jobs SET lease_token=?,lease_expires_at=?,
                           last_started_at=?,last_status='running',last_error_code=NULL,
                           updated_at=? WHERE job_id=? AND enabled=1
                           AND (lease_token IS NULL OR lease_expires_at<=?)""",
                        (token, expires, now_text, now_text, job_id, now_text),
                    )
                    if cursor.rowcount == 1:
                        self._db.execute(
                            """INSERT INTO automation_job_runs
                               (run_id,job_id,lease_token,started_at,status)
                               VALUES(?,?,?,?, 'running')""",
                            (run_id, job_id, token, now_text),
                        )
                        claims.append((job_id, token, run_id))
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

        for job_id, token, run_id in claims:
            stats["claimed"] += 1
            callback = self._callbacks.get(job_id)
            if callback is None:
                stats["unregistered"] += 1
                self._finish(job_id, token, run_id, succeeded=False, error_code="callback_unavailable")
                stats["failed"] += 1
                continue
            try:
                callback()
            except Exception as exc:
                self._finish(job_id, token, run_id, succeeded=False, error_code=type(exc).__name__[:80])
                stats["failed"] += 1
            else:
                self._finish(job_id, token, run_id, succeeded=True)
                stats["succeeded"] += 1
        return stats

    def _finish(
        self, job_id: str, token: str, run_id: str, *,
        succeeded: bool, error_code: str | None = None,
    ) -> None:
        now_text = _stamp(_now())
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT interval_seconds,consecutive_failures FROM automation_jobs "
                    "WHERE job_id=? AND lease_token=?",
                    (job_id, token),
                ).fetchone()
                if row is None:
                    self._db.execute("ROLLBACK")
                    return
                failures = 0 if succeeded else int(row["consecutive_failures"]) + 1
                backoff = min(
                    self.max_backoff_seconds,
                    max(1, int(row["interval_seconds"])) * (2 ** min(failures, 10)),
                )
                next_run = _now() + timedelta(
                    seconds=int(row["interval_seconds"]) if succeeded else backoff
                )
                status = "succeeded" if succeeded else "failed"
                self._db.execute(
                    """UPDATE automation_jobs SET lease_token=NULL,lease_expires_at=NULL,
                       last_finished_at=?,last_status=?,last_error_code=?,
                       consecutive_failures=?,next_run_at=?,updated_at=?
                       WHERE job_id=? AND lease_token=?""",
                    (now_text, status, error_code, failures, _stamp(next_run),
                     now_text, job_id, token),
                )
                self._db.execute(
                    """UPDATE automation_job_runs SET finished_at=?,status=?,error_code=?
                       WHERE run_id=? AND lease_token=? AND status='running'""",
                    (now_text, status, error_code, run_id, token),
                )
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def status(self) -> tuple[dict, ...]:
        """Return operational metadata only; never expose callback payloads."""
        with self._lock:
            rows = self._db.execute(
                """SELECT job_id,interval_seconds,enabled,next_run_at,lease_expires_at,
                   last_started_at,last_finished_at,last_status,last_error_code,
                   consecutive_failures FROM automation_jobs ORDER BY job_id"""
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def history(self, *, job_id: str | None = None, limit: int = 100) -> tuple[dict, ...]:
        """Return bounded, secret-free execution history, newest first."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        with self._lock:
            if job_id is None:
                rows = self._db.execute(
                    """SELECT run_id,job_id,started_at,finished_at,status,error_code
                       FROM automation_job_runs ORDER BY started_at DESC,run_id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                rows = self._db.execute(
                    """SELECT run_id,job_id,started_at,finished_at,status,error_code
                       FROM automation_job_runs WHERE job_id=?
                       ORDER BY started_at DESC,run_id DESC LIMIT ?""",
                    (job_id, limit),
                ).fetchall()
        return tuple(dict(row) for row in rows)
