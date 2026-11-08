"""SQLite-backed task worker with atomic claims and conservative lease recovery."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai_os.agent_runtime import agent_graph_enabled, run_agent_workflow
from ai_os.db import connect
from ai_os.model_adapter import generate_text


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_once(*, worker_id: str, lease_seconds: int = 900) -> dict:
    """Claim and process at most one queued task.

    Expired claims are moved to blocked for human review, never requeued
    automatically: a provider may have received a request before a worker died.
    """
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be greater than zero")

    claimed_at = _now()
    claimed_at_text = claimed_at.isoformat()
    lease_expires_at = (claimed_at + timedelta(seconds=lease_seconds)).isoformat()
    legacy_cutoff = (claimed_at - timedelta(seconds=lease_seconds)).isoformat()

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Recover expired leases conservatively. Older running rows predate the
        # lease column, so use their started_at timestamp as a fallback.
        db.execute(
            "UPDATE tasks SET status='blocked', "
            "error='Worker lease expired; manual review required before retry.', "
            "finished_at=?, lease_expires_at=NULL "
            "WHERE status='running' AND ("
            "(lease_expires_at IS NOT NULL AND lease_expires_at <= ?) OR "
            "(lease_expires_at IS NULL AND started_at IS NOT NULL AND started_at <= ?)"
            ")",
            (claimed_at_text, claimed_at_text, legacy_cutoff),
        )
        row = db.execute(
            "SELECT id,title,description,department FROM tasks "
            "WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return {"processed": False}
        task = dict(row)
        changed = db.execute(
            "UPDATE tasks SET status='running', worker_id=?, started_at=?, "
            "finished_at=NULL, lease_expires_at=?, error=NULL "
            "WHERE id=? AND status='queued'",
            (worker_id, claimed_at_text, lease_expires_at, task["id"]),
        ).rowcount
        if changed != 1:
            return {"processed": False}

    prompt = (
        "You are an assistant working for the " + task["department"] +
        " department. Complete this task carefully. Do not publish, spend money, "
        "contact customers, or change external systems. Return a concise result.\n\n"
        "Task: " + task["title"] + "\nDetails: " + task["description"]
    )
    try:
        if agent_graph_enabled():
            output = run_agent_workflow(task, worker_id=worker_id)
        else:
            output = generate_text(prompt)
    except Exception as exc:
        with connect() as db:
            db.execute(
                "UPDATE tasks SET status='failed', error=?, finished_at=?, "
                "lease_expires_at=NULL WHERE id=? AND status='running' AND worker_id=?",
                (f"{type(exc).__name__}: {str(exc)[:1000]}", _now().isoformat(),
                 task["id"], worker_id),
            )
        raise

    with connect() as db:
        changed = db.execute(
            "UPDATE tasks SET status='completed', result=?, error=NULL, "
            "finished_at=?, lease_expires_at=NULL "
            "WHERE id=? AND status='running' AND worker_id=?",
            (output, _now().isoformat(), task["id"], worker_id),
        ).rowcount
        if changed != 1:
            # Another worker may have marked this expired lease as blocked.
            # Do not overwrite that safety state with a late result.
            return {"processed": True, "task_id": task["id"], "status": "lease_lost"}
    return {"processed": True, "task_id": task["id"], "status": "completed"}
