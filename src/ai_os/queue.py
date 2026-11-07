"""SQLite-backed durable queue with idempotent enqueue and atomic claims."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.queue_schemas import JobCreate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(row) -> dict:
    item = dict(row)
    item["payload"] = json.loads(item["payload_json"])
    item["result"] = json.loads(item["result_json"]) if item["result_json"] else None
    del item["payload_json"]
    del item["result_json"]
    return item


def enqueue_job(payload: JobCreate) -> dict:
    now = _now()
    job_id = str(uuid4())
    encoded = json.dumps(payload.payload, separators=(",", ":"), sort_keys=True)
    with connect() as db:
        if payload.idempotency_key:
            existing = db.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?",
                (payload.idempotency_key,),
            ).fetchone()
            if existing:
                return _decode(existing)
        db.execute(
            """INSERT INTO jobs
            (id,job_type,payload_json,status,attempts,max_attempts,idempotency_key,
             created_at,updated_at)
            VALUES (?,?,?,'queued',0,3,?,?,?)""",
            (job_id, payload.job_type, encoded, payload.idempotency_key, now, now),
        )
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _decode(row)


def list_jobs(limit: int = 100) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_decode(row) for row in rows]


def claim_next_job(
    worker_id: str,
    lease_seconds: int = 120,
    allowed_job_types: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict | None:
    """Claim one eligible queued/retryable job; SQLite IMMEDIATE serializes claimers.

    When allowed_job_types is supplied, jobs outside that allowlist remain queued.
    This lets a worker continue safe local tasks while model-backed execution is
    disabled, without consuming and retrying specialist inference jobs.
    """
    if allowed_job_types is not None:
        allowed = sorted({item for item in allowed_job_types if isinstance(item, str) and item})
        if not allowed:
            return None
    else:
        allowed = None

    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    expired_before = (now - timedelta(seconds=lease_seconds)).isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """UPDATE jobs SET status='queued', locked_at=NULL, locked_by=NULL,
               updated_at=?
               WHERE status='running' AND locked_at < ? AND attempts < max_attempts""",
            (now_text, expired_before),
        )
        db.execute(
            """UPDATE jobs SET status='failed', error='Worker lease expired after maximum attempts',
               locked_at=NULL, locked_by=NULL, updated_at=?
               WHERE status='running' AND locked_at < ? AND attempts >= max_attempts""",
            (now_text, expired_before),
        )
        query = """SELECT id FROM jobs WHERE status='queued' AND attempts < max_attempts"""
        parameters: list = []
        if allowed is not None:
            placeholders = ",".join("?" for _ in allowed)
            query += f" AND job_type IN ({placeholders})"
            parameters.extend(allowed)
        query += " ORDER BY created_at ASC LIMIT 1"
        row = db.execute(query, parameters).fetchone()
        if row is None:
            return None
        job_id = row["id"]
        changed = db.execute(
            """UPDATE jobs SET status='running', attempts=attempts+1,
               locked_at=?, locked_by=?, updated_at=?
               WHERE id=? AND status='queued'""",
            (now_text, worker_id, now_text, job_id),
        ).rowcount
        if changed != 1:
            return None
        claimed = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _decode(claimed)


def finish_job(job_id: str, worker_id: str, result: dict) -> dict | None:
    now = _now()
    with connect() as db:
        db.execute(
            """UPDATE jobs SET status='completed', result_json=?, error=NULL,
               locked_at=NULL, locked_by=NULL, completed_at=?, updated_at=?
               WHERE id=? AND status='running' AND locked_by=?""",
            (json.dumps(result, separators=(",", ":"), sort_keys=True), now, now,
             job_id, worker_id),
        )
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _decode(row) if row else None


def fail_job(job_id: str, worker_id: str, error: str) -> dict | None:
    now = _now()
    with connect() as db:
        db.execute(
            """UPDATE jobs SET status=CASE WHEN attempts >= max_attempts
                    THEN 'failed' ELSE 'queued' END,
               error=?, locked_at=NULL, locked_by=NULL, updated_at=?
               WHERE id=? AND status='running' AND locked_by=?""",
            (error[:2000], now, job_id, worker_id),
        )
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _decode(row) if row else None


def renew_job_lease(job_id: str, worker_id: str, lease_seconds: int = 120) -> bool:
    """Extend a running job lease only for the worker that currently owns it."""
    now = _now()
    with connect() as db:
        changed = db.execute(
            """UPDATE jobs SET locked_at=?, updated_at=?
               WHERE id=? AND status='running' AND locked_by=?""",
            (now, now, job_id, worker_id),
        ).rowcount
    return changed == 1
