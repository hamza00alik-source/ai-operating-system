"""Durable, provider-neutral video generation job queue.

This module records approved work only. It does not call a provider, start a GPU,
spend money, or publish output. A separately deployed worker must claim queued jobs.
"""
import json
import uuid
from datetime import datetime, timezone

from ai_os.db import connect


def _now():
    return datetime.now(timezone.utc).isoformat()


def initialize():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS video_generation_jobs (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                prompt TEXT NOT NULL,
                parameters_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'awaiting_approval',
                estimated_cost_minor INTEGER NOT NULL,
                approved_budget_minor INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                cost_basis TEXT NOT NULL,
                approval_note TEXT NOT NULL DEFAULT '',
                provider_job_id TEXT,
                result_uri TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                started_at TEXT,
                finished_at TEXT
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_status_created ON video_generation_jobs(status, created_at)")


def create_job(*, prompt, parameters=None, provider="longcat-video", idempotency_key,
               estimated_cost_minor, approved_budget_minor, currency="USD", cost_basis):
    initialize()
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("A video prompt is required.")
    if len(prompt) > 8000:
        raise ValueError("Video prompt exceeds 8000 characters.")
    if not idempotency_key or len(idempotency_key) > 128:
        raise ValueError("A valid idempotency key is required.")
    if estimated_cost_minor < 0 or approved_budget_minor < 0:
        raise ValueError("Cost and budget must be non-negative integer minor units.")
    if not currency or len(currency) != 3 or not currency.isalpha():
        raise ValueError("Currency must be a three-letter code.")
    if not cost_basis.strip() or len(cost_basis) > 300:
        raise ValueError("A cost basis is required; unknown cost is not zero.")
    if not provider.strip() or len(provider) > 80:
        raise ValueError("A valid provider identifier is required.")
    job_id, now = str(uuid.uuid4()), _now()
    with connect() as db:
        existing = db.execute(
            "SELECT * FROM video_generation_jobs WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            same_request = (
                existing["provider"] == provider.strip()
                and existing["prompt"] == prompt
                and existing["parameters_json"] == json.dumps(parameters or {}, ensure_ascii=False, sort_keys=True)
                and existing["estimated_cost_minor"] == estimated_cost_minor
                and existing["approved_budget_minor"] == approved_budget_minor
                and existing["currency"] == currency.upper()
                and existing["cost_basis"] == cost_basis.strip()
            )
            if not same_request:
                raise ValueError("Idempotency key was already used for a different request.")
            return _serialize(existing)
        db.execute(
            """INSERT INTO video_generation_jobs
            (id,idempotency_key,provider,prompt,parameters_json,status,
             estimated_cost_minor,approved_budget_minor,currency,cost_basis,
             created_at,updated_at)
            VALUES (?,?,?,?,?,'awaiting_approval',?,?,?,?,?,?)""",
            (job_id, idempotency_key, provider.strip(), prompt,
             json.dumps(parameters or {}, ensure_ascii=False, sort_keys=True),
             estimated_cost_minor, approved_budget_minor, currency.upper(),
             cost_basis.strip(), now, now),
        )
    return get_job(job_id)


def get_job(job_id):
    initialize()
    with connect() as db:
        row = db.execute("SELECT * FROM video_generation_jobs WHERE id=?", (job_id,)).fetchone()
    return _serialize(row) if row else None


def list_jobs(status=None):
    initialize()
    with connect() as db:
        if status:
            rows = db.execute(
                "SELECT * FROM video_generation_jobs WHERE status=? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM video_generation_jobs ORDER BY created_at DESC").fetchall()
    return [_serialize(row) for row in rows]


def decide_job(job_id, decision, *, approval_note=""):
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    initialize()
    with connect() as db:
        row = db.execute("SELECT * FROM video_generation_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        if row["status"] != "awaiting_approval":
            raise ValueError("Only jobs awaiting approval can be decided.")
        if decision == "approved" and row["estimated_cost_minor"] > row["approved_budget_minor"]:
            raise ValueError("Estimated cost exceeds the explicitly approved budget.")
        now = _now()
        status = "queued" if decision == "approved" else "rejected"
        db.execute(
            """UPDATE video_generation_jobs SET status=?, approval_note=?,
               approved_at=?, updated_at=? WHERE id=? AND status='awaiting_approval'""",
            (status, approval_note.strip()[:1000], now, now, job_id),
        )
    return get_job(job_id)


def _serialize(row):
    return {
        "id": row["id"], "provider": row["provider"], "prompt": row["prompt"],
        "parameters": json.loads(row["parameters_json"]), "status": row["status"],
        "estimated_cost_minor": row["estimated_cost_minor"],
        "approved_budget_minor": row["approved_budget_minor"],
        "currency": row["currency"], "cost_basis": row["cost_basis"],
        "approval_note": row["approval_note"], "provider_job_id": row["provider_job_id"],
        "result_uri": row["result_uri"], "error": row["error"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "approved_at": row["approved_at"], "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }
