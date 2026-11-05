"""Task and approval business logic."""
from datetime import datetime, timezone
from uuid import uuid4
from ai_os.db import connect
from ai_os.schemas import ApprovalCreate, ApprovalDecision, TaskCreate

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_task(payload: TaskCreate) -> dict:
    task = {"id": str(uuid4()), "title": payload.title,
            "description": payload.description, "department": payload.department,
            "status": "queued", "created_at": _now()}
    with connect() as db:
        db.execute("""INSERT INTO tasks
            (id,title,description,department,status,created_at)
            VALUES (:id,:title,:description,:department,:status,:created_at)""", task)
    return task

def list_tasks() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]

def create_approval(payload: ApprovalCreate) -> dict:
    if payload.task_id:
        with connect() as db:
            exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (payload.task_id,)).fetchone()
        if not exists:
            raise LookupError("Task not found")
    approval = {"id": str(uuid4()), "task_id": payload.task_id,
                "action": payload.action, "details": payload.details,
                "status": "pending", "created_at": _now(), "decided_at": None}
    with connect() as db:
        db.execute("""INSERT INTO approvals
            (id,task_id,action,details,status,created_at,decided_at)
            VALUES (:id,:task_id,:action,:details,:status,:created_at,:decided_at)""", approval)
    return approval

def list_approvals() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM approvals ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]

def decide_approval(approval_id: str, payload: ApprovalDecision) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if row is None:
            return None
        if row["status"] != "pending":
            raise ValueError("This approval request has already been decided")
        decided_at = _now()
        db.execute("UPDATE approvals SET status=?, decided_at=? WHERE id=?",
                   (payload.decision, decided_at, approval_id))
        updated = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return dict(updated)
