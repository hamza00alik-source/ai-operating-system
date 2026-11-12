"""Authenticated, leased video-generation queue and worker protocol.

The API remains usable with zero workers. Workers only receive jobs that passed
owner approval; every worker mutation requires the shared worker secret and
the per-job lease token.
"""
import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from ai_os.db import connect


def _now():
    return datetime.now(timezone.utc)


def _iso(value=None):
    return (value or _now()).isoformat()


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def initialize():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS video_generation_jobs (
                id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL, prompt TEXT NOT NULL,
                parameters_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'awaiting_approval',
                estimated_cost_minor INTEGER NOT NULL,
                approved_budget_minor INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD', cost_basis TEXT NOT NULL,
                approval_note TEXT NOT NULL DEFAULT '', provider_job_id TEXT,
                result_uri TEXT, result_metadata_json TEXT NOT NULL DEFAULT '{}',
                error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                approved_at TEXT, started_at TEXT, finished_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
                lease_owner TEXT, lease_token_hash TEXT, lease_expires_at TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                progress REAL NOT NULL DEFAULT 0, progress_message TEXT NOT NULL DEFAULT ''
            )
        """)
        columns = {r["name"] for r in db.execute("PRAGMA table_info(video_generation_jobs)")}
        migrations = {
            "result_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            "attempts": "INTEGER NOT NULL DEFAULT 0", "max_attempts": "INTEGER NOT NULL DEFAULT 3",
            "lease_owner": "TEXT", "lease_token_hash": "TEXT", "lease_expires_at": "TEXT",
            "cancel_requested": "INTEGER NOT NULL DEFAULT 0", "progress": "REAL NOT NULL DEFAULT 0",
            "progress_message": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in migrations.items():
            if name not in columns:
                db.execute(f"ALTER TABLE video_generation_jobs ADD COLUMN {name} {definition}")
        db.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_status_created ON video_generation_jobs(status, created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_lease ON video_generation_jobs(status, lease_expires_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS video_generation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
            event TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_video_events_job ON video_generation_events(job_id,id)")


def _event(db, job_id, event, details=None):
    db.execute("INSERT INTO video_generation_events(job_id,event,details_json,created_at) VALUES(?,?,?,?)",
               (job_id,event,json.dumps(details or {},ensure_ascii=False),_iso()))


def create_job(*, prompt, parameters=None, provider="longcat-video", idempotency_key,
               estimated_cost_minor, approved_budget_minor, currency="USD", cost_basis,
               max_attempts=3):
    initialize()
    prompt = prompt.strip()
    if not prompt or len(prompt) > 8000: raise ValueError("Prompt must contain 1–8000 characters.")
    if not idempotency_key or len(idempotency_key) > 128: raise ValueError("A valid idempotency key is required.")
    if estimated_cost_minor < 0 or approved_budget_minor < 0: raise ValueError("Cost and budget must be non-negative integer minor units.")
    if not currency or len(currency) != 3 or not currency.isalpha(): raise ValueError("Currency must be a three-letter code.")
    if not cost_basis.strip() or len(cost_basis) > 300: raise ValueError("A cost basis is required; unknown cost is not zero.")
    if not provider.strip() or len(provider) > 80: raise ValueError("A valid provider identifier is required.")
    if not 1 <= max_attempts <= 5: raise ValueError("max_attempts must be between 1 and 5.")
    params_json = json.dumps(parameters or {},ensure_ascii=False,sort_keys=True)
    now, job_id = _iso(), str(uuid.uuid4())
    with connect() as db:
        existing = db.execute("SELECT * FROM video_generation_jobs WHERE idempotency_key=?",(idempotency_key,)).fetchone()
        if existing:
            same = (existing["provider"] == provider.strip() and existing["prompt"] == prompt
                    and existing["parameters_json"] == params_json
                    and existing["estimated_cost_minor"] == estimated_cost_minor
                    and existing["approved_budget_minor"] == approved_budget_minor
                    and existing["currency"] == currency.upper()
                    and existing["cost_basis"] == cost_basis.strip()
                    and existing["max_attempts"] == max_attempts)
            if not same: raise ValueError("Idempotency key was already used for a different request.")
            return _serialize(existing)
        db.execute("""INSERT INTO video_generation_jobs
            (id,idempotency_key,provider,prompt,parameters_json,status,estimated_cost_minor,
             approved_budget_minor,currency,cost_basis,max_attempts,created_at,updated_at)
            VALUES (?,?,?,?,?,'awaiting_approval',?,?,?,?,?,?,?)""",
            (job_id,idempotency_key,provider.strip(),prompt,params_json,estimated_cost_minor,
             approved_budget_minor,currency.upper(),cost_basis.strip(),max_attempts,now,now))
        _event(db,job_id,"created",{"provider":provider.strip()})
    return get_job(job_id)


def get_job(job_id):
    initialize()
    with connect() as db: row=db.execute("SELECT * FROM video_generation_jobs WHERE id=?",(job_id,)).fetchone()
    return _serialize(row) if row else None


def list_jobs(status=None):
    initialize()
    with connect() as db:
        rows=db.execute("SELECT * FROM video_generation_jobs"+(" WHERE status=?" if status else "")+" ORDER BY created_at DESC",
                        (status,) if status else ()).fetchall()
    return [_serialize(r) for r in rows]


def list_events(job_id):
    initialize()
    with connect() as db: rows=db.execute("SELECT * FROM video_generation_events WHERE job_id=? ORDER BY id",(job_id,)).fetchall()
    return [{"event":r["event"],"details":json.loads(r["details_json"]),"created_at":r["created_at"]} for r in rows]


def decide_job(job_id, decision, *, approval_note=""):
    if decision not in {"approved","rejected"}: raise ValueError("Decision must be approved or rejected.")
    initialize()
    with connect() as db:
        row=db.execute("SELECT * FROM video_generation_jobs WHERE id=?",(job_id,)).fetchone()
        if row is None: return None
        if row["status"]!="awaiting_approval": raise ValueError("Only jobs awaiting approval can be decided.")
        if decision=="approved" and row["estimated_cost_minor"]>row["approved_budget_minor"]:
            raise ValueError("Estimated cost exceeds the explicitly approved budget.")
        now=_iso(); status="queued" if decision=="approved" else "rejected"
        db.execute("UPDATE video_generation_jobs SET status=?,approval_note=?,approved_at=?,updated_at=? WHERE id=? AND status='awaiting_approval'",
                   (status,approval_note.strip()[:1000],now,now,job_id))
        _event(db,job_id,status,{"approval_note":approval_note.strip()[:1000]})
    return get_job(job_id)


def cancel_job(job_id):
    initialize()
    with connect() as db:
        row=db.execute("SELECT * FROM video_generation_jobs WHERE id=?",(job_id,)).fetchone()
        if row is None: return None
        if row["status"] in {"succeeded","failed","cancelled","rejected"}: raise ValueError("Terminal jobs cannot be cancelled.")
        now=_iso()
        if row["status"] in {"awaiting_approval","queued"}:
            db.execute("UPDATE video_generation_jobs SET status='cancelled',cancel_requested=1,finished_at=?,updated_at=? WHERE id=?",(now,now,job_id))
            _event(db,job_id,"cancelled",{"by":"owner"})
        else:
            db.execute("UPDATE video_generation_jobs SET cancel_requested=1,updated_at=? WHERE id=?",(now,job_id))
            _event(db,job_id,"cancel_requested",{"by":"owner"})
    return get_job(job_id)


def claim_job(worker_id, lease_seconds=120):
    if not worker_id or len(worker_id)>100: raise ValueError("worker_id must contain 1–100 characters.")
    if not 30<=lease_seconds<=900: raise ValueError("lease_seconds must be between 30 and 900.")
    initialize(); now=_now(); now_s=now.isoformat(); expires=(now+timedelta(seconds=lease_seconds)).isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expired=db.execute("SELECT * FROM video_generation_jobs WHERE status='running' AND lease_expires_at<=? ORDER BY created_at LIMIT 20",(now_s,)).fetchall()
        for row in expired:
            if row["cancel_requested"]:
                db.execute("UPDATE video_generation_jobs SET status='cancelled',finished_at=?,updated_at=?,lease_token_hash=NULL,lease_expires_at=NULL WHERE id=?",(now_s,now_s,row["id"]))
                _event(db,row["id"],"cancelled",{"reason":"lease_expired_after_cancel"})
            elif row["attempts"]>=row["max_attempts"]:
                db.execute("UPDATE video_generation_jobs SET status='failed',error='Worker lease expired; retry limit exhausted',finished_at=?,updated_at=?,lease_token_hash=NULL,lease_expires_at=NULL WHERE id=?",(now_s,now_s,row["id"]))
                _event(db,row["id"],"failed",{"reason":"lease_expired","attempts":row["attempts"]})
            else:
                db.execute("UPDATE video_generation_jobs SET status='queued',lease_owner=NULL,lease_token_hash=NULL,lease_expires_at=NULL,updated_at=?,error='Previous worker lease expired; queued for retry' WHERE id=?",(now_s,row["id"]))
                _event(db,row["id"],"lease_expired_retry",{"attempts":row["attempts"]})
        row=db.execute("SELECT * FROM video_generation_jobs WHERE status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1").fetchone()
        if row is None: return None
        token=secrets.token_urlsafe(32); attempt=row["attempts"]+1
        db.execute("""UPDATE video_generation_jobs SET status='running',attempts=?,lease_owner=?,
            lease_token_hash=?,lease_expires_at=?,started_at=COALESCE(started_at,?),updated_at=?,
            progress=0,progress_message='Worker claimed job',error=NULL WHERE id=? AND status='queued'""",
            (attempt,worker_id,_hash(token),expires,now_s,now_s,row["id"]))
        _event(db,row["id"],"claimed",{"worker_id":worker_id,"attempt":attempt,"lease_expires_at":expires})
        claimed=db.execute("SELECT * FROM video_generation_jobs WHERE id=?",(row["id"],)).fetchone()
    result=_serialize(claimed); result["lease_token"]=token
    return result


def _verify_lease(db,job_id,token):
    row=db.execute("SELECT * FROM video_generation_jobs WHERE id=?",(job_id,)).fetchone()
    if row is None: raise LookupError("Video job not found.")
    if row["status"]!="running" or not row["lease_token_hash"] or not secrets.compare_digest(row["lease_token_hash"],_hash(token or "")):
        raise PermissionError("Invalid or expired job lease token.")
    if row["lease_expires_at"]<=_iso(): raise PermissionError("Job lease has expired; worker must reclaim the job.")
    return row


def heartbeat(job_id,token,*,progress=None,message=""):
    initialize()
    with connect() as db:
        row=_verify_lease(db,job_id,token)
        if row["cancel_requested"]: return {"cancel_requested":True,"lease_expires_at":row["lease_expires_at"]}
        if progress is not None and not 0<=progress<=100: raise ValueError("progress must be between 0 and 100.")
        now=_now(); expires=(now+timedelta(seconds=int(os.getenv("VIDEO_JOB_LEASE_SECONDS","120")))).isoformat()
        db.execute("UPDATE video_generation_jobs SET lease_expires_at=?,updated_at=?,progress=COALESCE(?,progress),progress_message=? WHERE id=?",
                   (expires,now.isoformat(),progress,message[:240],job_id))
        _event(db,job_id,"heartbeat",{"progress":progress,"message":message[:240]})
    return {"cancel_requested":False,"lease_expires_at":expires}


def complete_job(job_id,token,*,result_uri,metadata=None):
    if not result_uri.startswith("https://") or len(result_uri)>2048: raise ValueError("Result must be stored at a private HTTPS artifact URL.")
    initialize()
    with connect() as db:
        row=_verify_lease(db,job_id,token)
        if row["cancel_requested"]: raise ValueError("Cancellation was requested; do not mark this job successful.")
        now=_iso()
        db.execute("""UPDATE video_generation_jobs SET status='succeeded',result_uri=?,result_metadata_json=?,
            progress=100,progress_message='Completed',finished_at=?,updated_at=?,lease_token_hash=NULL,lease_expires_at=NULL
            WHERE id=?""",(result_uri,json.dumps(metadata or {},ensure_ascii=False),now,now,job_id))
        _event(db,job_id,"succeeded",{"result_uri":result_uri,"metadata":metadata or {}})
    return get_job(job_id)


def fail_job(job_id,token,*,error,retryable=True):
    initialize()
    with connect() as db:
        row=_verify_lease(db,job_id,token); now=_iso()
        if row["cancel_requested"]: status="cancelled"
        elif retryable and row["attempts"]<row["max_attempts"]: status="queued"
        else: status="failed"
        finished=now if status in {"cancelled","failed"} else None
        db.execute("""UPDATE video_generation_jobs SET status=?,error=?,updated_at=?,finished_at=?,
            lease_owner=NULL,lease_token_hash=NULL,lease_expires_at=NULL WHERE id=?""",
            (status,error[:2000],now,finished,job_id))
        _event(db,job_id,status,{"error":error[:500],"retryable":retryable,"attempt":row["attempts"]})
    return get_job(job_id)


def worker_status():
    return {"configured":bool(os.getenv("VIDEO_WORKER_TOKEN","").strip()),"worker_protocol":"lease-v1",
            "provider":"longcat-video","generation_enabled":False,
            "note":"A separately deployed GPU worker must connect; API remains independent."}


def _serialize(row):
    return {"id":row["id"],"provider":row["provider"],"prompt":row["prompt"],
        "parameters":json.loads(row["parameters_json"]),"status":row["status"],
        "estimated_cost_minor":row["estimated_cost_minor"],"approved_budget_minor":row["approved_budget_minor"],
        "currency":row["currency"],"cost_basis":row["cost_basis"],"approval_note":row["approval_note"],
        "provider_job_id":row["provider_job_id"],"result_uri":row["result_uri"],
        "result_metadata":json.loads(row["result_metadata_json"] or "{}"),"error":row["error"],
        "created_at":row["created_at"],"updated_at":row["updated_at"],"approved_at":row["approved_at"],
        "started_at":row["started_at"],"finished_at":row["finished_at"],"attempts":row["attempts"],
        "max_attempts":row["max_attempts"],"lease_owner":row["lease_owner"],
        "lease_expires_at":row["lease_expires_at"],"cancel_requested":bool(row["cancel_requested"]),
        "progress":row["progress"],"progress_message":row["progress_message"]}
