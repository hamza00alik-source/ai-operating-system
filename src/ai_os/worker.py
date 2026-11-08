"""Durable, lease-based task execution using the configured model adapter."""
from datetime import datetime, timedelta, timezone

from ai_os.db import connect
from ai_os.model_adapter import ModelAdapterError, chat_completion


LEASE_MINUTES = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _task_prompt(task: dict) -> str:
    return (
        "You are an execution worker inside a human-supervised AI operating system. "
        "Complete the requested task and return a concise, useful result. "
        "Do not claim to have performed external actions, purchases, publishing, "
        "account changes, or deployments. If the task requires such an action, "
        "prepare instructions or a draft and explicitly state that human approval "
        "and a separate authorized integration are required.\n\n"
        f"Department: {task['department']}\n"
        f"Task: {task['title']}\n"
        f"Description: {task['description']}"
    )


def _claim_task(worker_id: str) -> dict | None:
    now = _now()
    now_text = now.isoformat()
    lease = (now + timedelta(minutes=LEASE_MINUTES)).isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT * FROM tasks
               WHERE status='queued' AND attempts < max_attempts
               ORDER BY created_at ASC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        changed = db.execute(
            """UPDATE tasks SET status='running', worker_id=?,
               lease_expires_at=?, started_at=?, attempts=attempts+1,
               error=NULL
               WHERE id=? AND status='queued'""",
            (worker_id, lease, now_text, row["id"]),
        ).rowcount
        if changed != 1:
            return None
        claimed = db.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone()
        return dict(claimed)


def run_once(*, worker_id: str) -> dict:
    """Claim and process at most one task; return safely if queue is empty."""
    task = _claim_task(worker_id)
    if task is None:
        return {"processed": False, "reason": "queue_empty"}

    try:
        model_result = chat_completion(_task_prompt(task))
    except ModelAdapterError as exc:
        now_text = _now().isoformat()
        retry = task["attempts"] < task["max_attempts"]
        with connect() as db:
            db.execute(
                """UPDATE tasks SET status=?, error=?, worker_id=NULL,
                   lease_expires_at=NULL, completed_at=?
                   WHERE id=? AND status='running' AND worker_id=?""",
                (
                    "queued" if retry else "failed",
                    str(exc)[:1000],
                    None if retry else now_text,
                    task["id"],
                    worker_id,
                ),
            )
        return {
            "processed": True,
            "task_id": task["id"],
            "status": "queued" if retry else "failed",
            "error": str(exc),
        }

    now_text = _now().isoformat()
    with connect() as db:
        updated = db.execute(
            """UPDATE tasks SET status='completed', result=?, error=NULL,
               worker_id=NULL, lease_expires_at=NULL, completed_at=?
               WHERE id=? AND status='running' AND worker_id=?""",
            (model_result["response"], now_text, task["id"], worker_id),
        ).rowcount
    if updated != 1:
        return {
            "processed": True,
            "task_id": task["id"],
            "status": "lease_lost",
        }
    return {
        "processed": True,
        "task_id": task["id"],
        "status": "completed",
        "provider": model_result["provider"],
        "model": model_result["model"],
        "latency_ms": model_result["latency_ms"],
    }
