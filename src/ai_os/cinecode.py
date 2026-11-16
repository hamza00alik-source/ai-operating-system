"""Owner-approved Cinecode render queue for the native AIOS application.

Jobs are inert until an owner approves them. Execution is a separate, opt-in
local worker; generated artifacts remain private and are served only to owners.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from ai_os.auth import require_owner_key
from ai_os.db import connect

router = APIRouter(tags=["cinecode"])
MAX_ARTIFACT_BYTES = 250 * 1024 * 1024
JOB_MODES = {"quick", "film"}
MUSIC_SOURCES = {"none", "code"}
JOB_STATES = {"pending_approval", "rejected", "approved", "running", "succeeded", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_cinecode() -> None:
    """Create the small Cinecode schema without changing existing AIOS tables."""
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS cinecode_jobs (
                id TEXT PRIMARY KEY,
                brief TEXT NOT NULL,
                mode TEXT NOT NULL,
                music_source TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                started_at TEXT,
                finished_at TEXT,
                worker_id TEXT,
                progress TEXT NOT NULL DEFAULT 'Waiting for owner approval',
                error TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                artifact_path TEXT,
                artifact_sha256 TEXT,
                artifact_bytes INTEGER,
                report_path TEXT
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_cinecode_jobs_status_created ON cinecode_jobs(status, created_at)")

def _job(row) -> dict:
    item = dict(row)
    item.pop("artifact_path", None)
    item.pop("report_path", None)
    item["cancel_requested"] = bool(item.get("cancel_requested"))
    return item


class CinecodeJobCreate(BaseModel):
    brief: str = Field(min_length=20, max_length=12000)
    mode: str = Field(default="quick", pattern="^(quick|film)$")
    music_source: str = Field(pattern="^(none|code)$")


def _get_job(job_id: str):
    with connect() as db:
        return db.execute("SELECT * FROM cinecode_jobs WHERE id=?", (job_id,)).fetchone()


@router.get("/cinecode", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(require_owner_key)])
def cinecode_console():
    return HTMLResponse("""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIOS · Cinecode Studio</title>
<style>
body{font:16px system-ui;background:#0b1020;color:#edf3ff;max-width:900px;margin:32px auto;padding:0 16px}
section{background:#121a2d;border:1px solid #26334d;border-radius:14px;padding:18px;margin:16px 0}
textarea,input,select,button{font:inherit;padding:10px;border-radius:8px;border:1px solid #405070;background:#0c1425;color:inherit}
textarea{width:calc(100% - 24px);min-height:120px}button{cursor:pointer;background:#263d75;margin:4px}
.job{border-top:1px solid #26334d;padding:12px 0}.muted{color:#9aa9c3}a{color:#9bb8ff}
</style>
<h1>Cinecode Studio</h1><p class="muted">Create a brief, review it, then explicitly approve rendering. Jobs are private; publishing is not enabled. Codex account usage may incur charges; AIOS cannot estimate or cap provider-side usage. Approve only after a separate service account and hard spend cap are verified.</p>
<section><h2>New film brief</h2><form id="create">
<textarea id="brief" minlength="20" maxlength="12000" required placeholder="Describe the film, audience, visual direction, scenes, narration and desired result..."></textarea><p>
<label>Mode <select id="mode"><option value="quick">Quick (lower resource use)</option><option value="film">Film</option></select></label>
<label>Music <select id="music"><option value="none">No music</option><option value="code">Original code-generated music</option></select></label>
</p><button>Create draft job</button></form><p id="message" class="muted"></p></section>
<section><h2>Render queue</h2><button id="refresh">Refresh</button><div id="jobs"></div></section>
<script>
const $=id=>document.getElementById(id), msg=t=>$('message').textContent=t;
async function call(url,method='GET',body){const r=await fetch(url,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});const d=await r.json().catch(()=>({detail:r.statusText}));if(!r.ok)throw Error(d.detail||r.statusText);return d}
$('create').addEventListener('submit',async e=>{e.preventDefault();try{const j=await call('/cinecode/jobs','POST',{brief:$('brief').value,mode:$('mode').value,music_source:$('music').value});msg('Draft created. Review the brief below and approve only when ready.');$('brief').value='';await refresh()}catch(x){msg(x.message)}});
async function action(id,a){if(a==='approve'&&!window.confirm('Approve this local render? This may consume Codex service-account usage. Confirm that the separate account, usage terms and hard spend cap have been checked.'))return;try{await call('/cinecode/jobs/'+id+'/'+a,'POST',{});await refresh()}catch(x){msg(x.message)}}
async function refresh(){try{const d=await call('/cinecode/jobs');$('jobs').innerHTML=d.jobs.map(j=>'<div class="job"><b>'+escapeHtml(j.mode.toUpperCase())+' · '+escapeHtml(j.status)+'</b><p>'+escapeHtml(j.brief)+'</p><p class="muted">'+escapeHtml(j.progress||'')+(j.error?' · '+escapeHtml(j.error):'')+'</p>'+ (j.status==='pending_approval'?'<button data-job="'+j.id+'" data-action="approve">Approve render</button><button data-job="'+j.id+'" data-action="reject">Reject</button>':'') + (['approved','running'].includes(j.status)?'<button data-job="'+j.id+'" data-action="cancel">Cancel</button>':'') + (j.status==='succeeded'?'<a href="/cinecode/jobs/'+j.id+'/artifact">Download private MP4</a> · <a href="/cinecode/jobs/'+j.id+'/report">Production report</a>':'')+'</div>').join('')||'<p class="muted">No jobs yet.</p>';$('jobs').querySelectorAll('button[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.job,b.dataset.action)));}catch(x){msg(x.message)}}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
$('refresh').addEventListener('click',refresh);refresh();
</script></html>""")


@router.post("/cinecode/jobs", status_code=201, dependencies=[Depends(require_owner_key)])
def create_cinecode_job(payload: CinecodeJobCreate):
    initialize_cinecode()
    job_id = str(uuid.uuid4())
    now = _now()
    with connect() as db:
        db.execute(
            """INSERT INTO cinecode_jobs
            (id,brief,mode,music_source,status,created_at,updated_at,progress)
            VALUES (?,?,?,?,?,?,?,?)""",
            (job_id, payload.brief.strip(), payload.mode, payload.music_source,
             "pending_approval", now, now, "Waiting for owner approval"),
        )

    return _job(_get_job(job_id))


@router.get("/cinecode/jobs", dependencies=[Depends(require_owner_key)])
def list_cinecode_jobs():
    initialize_cinecode()
    with connect() as db:
        rows = db.execute("SELECT * FROM cinecode_jobs ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"jobs": [_job(row) for row in rows]}


@router.get("/cinecode/jobs/{job_id}", dependencies=[Depends(require_owner_key)])
def get_cinecode_job(job_id: str):
    initialize_cinecode()
    row = _get_job(job_id)
    if row is None:
        raise HTTPException(404, "Cinecode job not found.")
    return _job(row)


@router.post("/cinecode/jobs/{job_id}/approve", dependencies=[Depends(require_owner_key)])
def approve_cinecode_job(job_id: str):
    initialize_cinecode()
    now = _now()
    with connect() as db:
        result = db.execute(
            """UPDATE cinecode_jobs SET status='approved',approved_at=?,updated_at=?,
               progress='Owner approved; waiting for an explicitly enabled local worker'
               WHERE id=? AND status='pending_approval'""",
            (now, now, job_id),
        )

    if result.rowcount != 1:
        row = _get_job(job_id)
        if row is None:
            raise HTTPException(404, "Cinecode job not found.")
        raise HTTPException(409, "Only a pending job can be approved.")
    return _job(_get_job(job_id))


@router.post("/cinecode/jobs/{job_id}/reject", dependencies=[Depends(require_owner_key)])
def reject_cinecode_job(job_id: str):
    initialize_cinecode()
    now = _now()
    with connect() as db:
        result = db.execute(
            "UPDATE cinecode_jobs SET status='rejected',updated_at=?,finished_at=?,progress='Rejected by owner' WHERE id=? AND status='pending_approval'",
            (now, now, job_id),
        )

    if result.rowcount != 1:
        row = _get_job(job_id)
        if row is None:
            raise HTTPException(404, "Cinecode job not found.")
        raise HTTPException(409, "Only a pending job can be rejected.")
    return _job(_get_job(job_id))


@router.post("/cinecode/jobs/{job_id}/cancel", dependencies=[Depends(require_owner_key)])
def cancel_cinecode_job(job_id: str):
    initialize_cinecode()
    now = _now()
    with connect() as db:
        result = db.execute(
            """UPDATE cinecode_jobs SET status=CASE WHEN status='running' THEN status ELSE 'cancelled' END,
               cancel_requested=1,updated_at=?,progress='Cancellation requested by owner'
               WHERE id=? AND status IN ('approved','running')""",
            (now, job_id),
        )

    if result.rowcount != 1:
        row = _get_job(job_id)
        if row is None:
            raise HTTPException(404, "Cinecode job not found.")
        raise HTTPException(409, "Only approved or running jobs can be cancelled.")
    return _job(_get_job(job_id))


@router.get("/cinecode/jobs/{job_id}/artifact", dependencies=[Depends(require_owner_key)])
def download_cinecode_artifact(job_id: str):
    initialize_cinecode()
    row = _get_job(job_id)
    if row is None:
        raise HTTPException(404, "Cinecode job not found.")
    if row["status"] != "succeeded" or not row["artifact_path"]:
        raise HTTPException(409, "A validated completed MP4 is not available.")
    path = Path(row["artifact_path"]).resolve()
    root = Path(os.getenv("AI_OS_CINECODE_STORAGE_DIR", "/data/cinecode")).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Private artifact is unavailable.")
    return FileResponse(path, media_type="video/mp4", filename=f"cinecode-{job_id}.mp4",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/cinecode/jobs/{job_id}/report", dependencies=[Depends(require_owner_key)])
def download_cinecode_report(job_id: str):
    initialize_cinecode()
    row = _get_job(job_id)
    if row is None:
        raise HTTPException(404, "Cinecode job not found.")
    if row["status"] != "succeeded" or not row["report_path"]:
        raise HTTPException(409, "A completed production report is not available.")
    path = Path(row["report_path"]).resolve()
    root = Path(os.getenv("AI_OS_CINECODE_STORAGE_DIR", "/data/cinecode")).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Private production report is unavailable.")
    return FileResponse(path, media_type="text/markdown", filename=f"cinecode-{job_id}-report.md",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/cinecode/status", dependencies=[Depends(require_owner_key)])
def cinecode_status():
    initialize_cinecode()
    with connect() as db:
        counts = db.execute("SELECT status,COUNT(*) AS count FROM cinecode_jobs GROUP BY status").fetchall()
    return {
        "provider": "cinecode",
        "execution_enabled": os.getenv("AI_OS_CINECODE_EXECUTION_ENABLED", "").lower() == "true",
        "billing_confirmed": os.getenv("AI_OS_CINECODE_BILLING_CONFIRMED", "").lower() == "true",
        "worker_mode": "separate local worker; disabled unless both gates are true",
        "job_counts": {row["status"]: row["count"] for row in counts},
        "publishing": "not integrated; owner review and separate publishing approval required",
    }
