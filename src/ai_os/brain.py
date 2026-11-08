"""Provider-independent persistent memory for the AIOS company brain."""
from datetime import datetime, timezone
from uuid import uuid4
import re
from ai_os.db import connect

def _now():
    return datetime.now(timezone.utc).isoformat()

def _terms(value):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (value or "").casefold())}

def retrieve_memories(query: str, department: str = "general", limit: int = 5) -> list[dict]:
    terms = _terms(query)
    if not terms:
        return []
    with connect() as db:
        rows = db.execute("""SELECT id,category,department,title,content,confidence,created_at
            FROM brain_memories WHERE status='approved' AND department IN (?, 'general')
            ORDER BY created_at DESC LIMIT 500""", (department,)).fetchall()
    ranked = []
    for row in rows:
        item = dict(row)
        overlap = len(terms & _terms(item["title"] + " " + item["content"]))
        if overlap:
            item["relevance"] = overlap / len(terms)
            ranked.append(item)
    ranked.sort(key=lambda x: (x["relevance"], x["confidence"], x["created_at"]), reverse=True)
    return ranked[:max(1, min(limit, 10))]

def record_experience(run_id: str, task_id: str, department: str, title: str, outcome: str) -> str:
    experience_id, memory_id, now = str(uuid4()), str(uuid4()), _now()
    outcome = (outcome or "").strip()[:12000]
    with connect() as db:
        db.execute("""INSERT INTO brain_experiences
            (id,run_id,task_id,department,task_title,outcome,created_at) VALUES(?,?,?,?,?,?,?)""",
            (experience_id, run_id, task_id, department or "general", title[:300], outcome, now))
        if outcome:
            db.execute("""INSERT INTO brain_memories
                (id,category,department,title,content,source_run_id,status,confidence,created_at)
                VALUES(?,'lesson',?,?,?,?, 'proposed',0.35,?)""",
                (memory_id, department or "general", ("Experience: " + title)[:300], outcome[:4000], run_id, now))
    return experience_id

def brain_status() -> dict:
    with connect() as db:
        experiences = db.execute("SELECT COUNT(*) n FROM brain_experiences").fetchone()["n"]
        counts = {r["status"]: r["n"] for r in db.execute("SELECT status,COUNT(*) n FROM brain_memories GROUP BY status")}
        departments = [dict(r) for r in db.execute("SELECT department,COUNT(*) n FROM brain_experiences GROUP BY department ORDER BY n DESC")]
    return {"architecture":"local-persistent-experience-memory","learning_mode":"automatic experience capture; owner-approved reusable memories",
        "provider_independent":True,"uses_embeddings_or_extra_model_calls":False,"experiences":experiences,
        "memories":{"proposed":counts.get("proposed",0),"approved":counts.get("approved",0),"rejected":counts.get("rejected",0)},
        "departments":departments,"limitations":"Persistent memory and retrieval, not training a new neural network or independent general reasoning."}

def list_memories(status: str | None = None, limit: int = 100) -> list[dict]:
    with connect() as db:
        if status in {"proposed","approved","rejected"}:
            rows = db.execute("""SELECT id,category,department,title,content,source_run_id,status,confidence,
                created_at,reviewed_at,review_note FROM brain_memories WHERE status=? ORDER BY created_at DESC LIMIT ?""",
                (status,max(1,min(limit,200)))).fetchall()
        else:
            rows = db.execute("""SELECT id,category,department,title,content,source_run_id,status,confidence,
                created_at,reviewed_at,review_note FROM brain_memories ORDER BY created_at DESC LIMIT ?""",
                (max(1,min(limit,200)),)).fetchall()
    return [dict(r) for r in rows]

def review_memory(memory_id: str, decision: str, note: str = "") -> dict | None:
    if decision not in {"approved","rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    with connect() as db:
        cur = db.execute("""UPDATE brain_memories SET status=?,reviewed_at=?,review_note=?
            WHERE id=? AND status='proposed'""",(decision,_now(),(note or "")[:1000],memory_id))
        if not cur.rowcount:
            return None
        row = db.execute("""SELECT id,category,department,title,content,source_run_id,status,confidence,
            created_at,reviewed_at,review_note FROM brain_memories WHERE id=?""",(memory_id,)).fetchone()
    return dict(row)
