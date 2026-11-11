"""Business-scoped persistent memory for the shared AIOS reasoning engine."""
from datetime import datetime, timezone, timedelta
import json
from uuid import uuid4
import re
from ai_os.db import connect

from ai_os.business_registry import BUSINESS_IDS

def _business_id(value: str) -> str:
    value = (value or "core").strip()
    if value not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    return value

def _now():
    return datetime.now(timezone.utc).isoformat()

def _terms(value):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (value or "").casefold())}

def retrieve_memories(query: str, department: str = "general", limit: int = 5, business_id: str = "core") -> list[dict]:
    """Retrieve approved memories from exactly one business; never fall back across businesses."""
    scope = _business_id(business_id)
    terms = _terms(query)
    if not terms:
        return []
    with connect() as db:
        rows = db.execute("""SELECT id,business_id,category,department,title,content,confidence,created_at
            FROM brain_memories WHERE status='approved' AND business_id=? AND department IN (?, 'general')
            ORDER BY created_at DESC LIMIT 500""", (scope, department)).fetchall()
    ranked = []
    for row in rows:
        item = dict(row)
        overlap = len(terms & _terms(item["title"] + " " + item["content"]))
        if overlap:
            item["relevance"] = overlap / len(terms)
            ranked.append(item)
    ranked.sort(key=lambda x: (x["relevance"], x["confidence"], x["created_at"]), reverse=True)
    return ranked[:max(1, min(limit, 10))]

def record_experience(run_id: str, task_id: str, department: str, title: str, outcome: str, business_id: str = "core") -> str:
    scope = _business_id(business_id)
    experience_id, memory_id, now = str(uuid4()), str(uuid4()), _now()
    outcome = (outcome or "").strip()[:12000]
    with connect() as db:
        db.execute("""INSERT INTO brain_experiences
            (id,run_id,task_id,business_id,department,task_title,outcome,created_at) VALUES(?,?,?,?,?,?,?,?)""",
            (experience_id, run_id, task_id, scope, department or "general", title[:300], outcome, now))
        if outcome:
            db.execute("""INSERT INTO brain_memories
                (id,business_id,category,department,title,content,source_run_id,status,confidence,created_at)
                VALUES(?,?,'lesson',?,?,?,?, 'proposed',0.35,?)""",
                (memory_id, scope, department or "general", ("Experience: " + title)[:300], outcome[:4000], run_id, now))
    return experience_id


def record_failure_experience(run_id: str, task_id: str, department: str, title: str, error: str, business_id: str = "core") -> str:
    """Capture failed/partial execution metadata without treating the error as trusted knowledge."""
    scope = _business_id(business_id)
    experience_id, now = str(uuid4()), _now()
    safe_error = re.sub(r"[\r\n\t]+", " ", (error or "Unknown execution failure")).strip()[:1000]
    with connect() as db:
        db.execute("""INSERT INTO brain_experiences
            (id,run_id,task_id,business_id,department,task_title,outcome,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (experience_id, run_id, task_id, scope, department or "general",
             ("[FAILED] " + (title or "Untitled task"))[:300],
             "[FAILED] " + safe_error, now))
    return experience_id


def run_learning_cycle(business_id: str = "core", lookback_days: int = 30) -> dict:
    """Autonomously evaluate execution telemetry and create evidence-labelled improvement proposals.

    This cycle never changes code, credentials, provider billing, customer data, or external accounts.
    Proposed operational changes remain owner-reviewed before they can influence agent memory.
    """
    scope = _business_id(business_id)
    days = max(1, min(int(lookback_days), 90))
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()
    cycle_key = "brain-cycle:" + scope + ":" + now.strftime("%Y%m%d%H")
    cycle_id = str(uuid4())
    proposals = []
    with connect() as db:
        existing = db.execute(
            "SELECT id FROM brain_experiences WHERE business_id=? AND run_id=?",
            (scope, cycle_key),
        ).fetchone()
        if existing:
            return {"business_id": scope, "already_ran": True, "proposals_created": 0,
                    "cycle_id": cycle_key, "lookback_days": days}

        rows = db.execute("""SELECT t.department, r.status, COUNT(*) AS total
            FROM agent_runs r JOIN tasks t ON t.id=r.task_id
            WHERE t.business_id=? AND r.created_at>=?
            GROUP BY t.department, r.status ORDER BY t.department, r.status""",
            (scope, cutoff)).fetchall()
        metrics = {}
        for row in rows:
            item = metrics.setdefault(row["department"] or "general",
                                      {"total": 0, "completed": 0, "failed": 0, "partial": 0,
                                       "queued": 0, "running": 0})
            status = row["status"]
            item["total"] += row["total"]
            if status in item:
                item[status] += row["total"]
            elif status in {"crashed", "cancelled"}:
                item["failed"] += row["total"]

        for department, counts in metrics.items():
            observed = counts["completed"] + counts["failed"] + counts["partial"]
            if observed < 3:
                continue
            failures = counts["failed"] + counts["partial"]
            rate = failures / observed
            if failures:
                kind = "reliability"
                title = "Reliability review: " + department
                content = (
                    f"Autonomous operational evaluation over the last {days} days observed "
                    f"{observed} finished runs in {department}: {counts['completed']} completed, "
                    f"{counts['partial']} partial, and {counts['failed']} failed "
                    f"(observed failure/partial rate {rate:.0%}). This is a measured signal, "
                    "not a causal diagnosis. Review the corresponding run events and provider "
                    "errors, identify recurring causes, then propose a tested workflow or prompt improvement."
                )
                confidence = min(0.85, 0.55 + min(observed, 10) * 0.02)
            else:
                kind = "consistency"
                title = "Consistency review: " + department
                content = (
                    f"Autonomous operational evaluation observed {observed} completed runs in "
                    f"{department} and no failed or partial runs during the last {days} days. "
                    "This is a limited sample, not proof of general reliability. Preserve the "
                    "successful workflow and compare future outcomes before changing it."
                )
                confidence = min(0.8, 0.5 + min(observed, 10) * 0.02)
            source_key = cycle_key + ":" + department + ":" + kind
            exists = db.execute(
                "SELECT id FROM brain_memories WHERE business_id=? AND source_run_id=?",
                (scope, source_key),
            ).fetchone()
            if not exists:
                memory_id = str(uuid4())
                db.execute("""INSERT INTO brain_memories
                    (id,business_id,category,department,title,content,source_run_id,status,confidence,created_at)
                    VALUES(?,?,'improvement',?,?,?,?, 'proposed',?,?)""",
                    (memory_id, scope, department, title, content, source_key, confidence, now.isoformat()))
                proposals.append({"id": memory_id, "department": department, "category": kind,
                                  "observed_runs": observed, "failure_rate": round(rate, 3)})

        summary = {"lookback_days": days, "departments": metrics, "proposals_created": len(proposals)}
        db.execute("""INSERT INTO brain_experiences
            (id,run_id,task_id,business_id,department,task_title,outcome,created_at)
            VALUES(?,?,NULL,?,'system','Autonomous learning cycle',?,?)""",
            (cycle_id, cycle_key, scope, json.dumps(summary, sort_keys=True), now.isoformat()))
    return {"business_id": scope, "already_ran": False, "cycle_id": cycle_key,
            "lookback_days": days, "departments_evaluated": len(metrics),
            "proposals_created": len(proposals), "proposals": proposals}



def brain_status(business_id: str = "core") -> dict:
    scope = _business_id(business_id)
    with connect() as db:
        experiences = db.execute("""SELECT COUNT(*) n FROM brain_experiences
            WHERE business_id=? AND task_title<>'Autonomous learning cycle'""", (scope,)).fetchone()["n"]
        counts = {r["status"]: r["n"] for r in db.execute("SELECT status,COUNT(*) n FROM brain_memories WHERE business_id=? GROUP BY status", (scope,))}
        departments = [dict(r) for r in db.execute("""SELECT department,COUNT(*) n FROM brain_experiences
            WHERE business_id=? AND task_title<>'Autonomous learning cycle'
            GROUP BY department ORDER BY n DESC""", (scope,))]
        cycle = db.execute("""SELECT created_at,outcome FROM brain_experiences
            WHERE business_id=? AND task_title='Autonomous learning cycle'
            ORDER BY created_at DESC LIMIT 1""", (scope,)).fetchone()
        cycle_count = db.execute("""SELECT COUNT(*) n FROM brain_experiences
            WHERE business_id=? AND task_title='Autonomous learning cycle'""", (scope,)).fetchone()["n"]
        improvement_count = db.execute("""SELECT COUNT(*) n FROM brain_memories
            WHERE business_id=? AND category='improvement' AND status='proposed'""", (scope,)).fetchone()["n"]
    last_cycle = None
    if cycle:
        try:
            last_cycle = {"created_at": cycle["created_at"], "summary": json.loads(cycle["outcome"])}
        except (TypeError, ValueError):
            last_cycle = {"created_at": cycle["created_at"], "summary": {}}
    return {"business_id": scope, "architecture": "shared-reasoning-engine-with-isolated-business-memory",
        "learning_mode": "autonomous execution telemetry evaluation every 6 hours; automatic experience capture; owner-reviewed improvement proposals",
        "provider_independent": True, "uses_embeddings_or_extra_model_calls": False, "experiences": experiences,
        "memories": {"proposed": counts.get("proposed", 0), "approved": counts.get("approved", 0), "rejected": counts.get("rejected", 0)},
        "autonomy": {"learning_cycles": cycle_count, "last_cycle": last_cycle,
                     "pending_improvement_proposals": improvement_count,
                     "automatic_code_changes": False, "external_actions": "owner approval required"},
        "departments": departments,
        "limitations": "The brain autonomously captures and evaluates operational evidence and proposes improvements. It does not retrain the foundation model or deploy self-modified code."}

def list_memories(status: str | None = None, limit: int = 100, business_id: str = "core") -> list[dict]:
    scope = _business_id(business_id)
    with connect() as db:
        if status in {"proposed", "approved", "rejected"}:
            rows = db.execute("""SELECT id,business_id,category,department,title,content,source_run_id,status,confidence,
                created_at,reviewed_at,review_note FROM brain_memories WHERE business_id=? AND status=? ORDER BY created_at DESC LIMIT ?""",
                (scope, status, max(1, min(limit, 200)))).fetchall()
        else:
            rows = db.execute("""SELECT id,business_id,category,department,title,content,source_run_id,status,confidence,
                created_at,reviewed_at,review_note FROM brain_memories WHERE business_id=? ORDER BY created_at DESC LIMIT ?""",
                (scope, max(1, min(limit, 200)))).fetchall()
    return [dict(r) for r in rows]

def review_memory(memory_id: str, decision: str, note: str = "") -> dict | None:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    with connect() as db:
        cur = db.execute("UPDATE brain_memories SET status=?,reviewed_at=?,review_note=? WHERE id=? AND status='proposed'",
            (decision, _now(), (note or "")[:1000], memory_id))
        if not cur.rowcount:
            return None
        row = db.execute("""SELECT id,business_id,category,department,title,content,source_run_id,status,confidence,
            created_at,reviewed_at,review_note FROM brain_memories WHERE id=?""", (memory_id,)).fetchone()
    return dict(row)
