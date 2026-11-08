"""SQLite-backed task worker with atomic claiming and retryable failures."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from ai_os.db import connect
from ai_os.model_adapter import generate_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_once(*, worker_id: str) -> dict:
    """Claim and process at most one queued task.

    A task is marked failed on provider errors; a later retry policy can requeue
    it after classifying transient versus permanent failures. This starter does
    not automatically repeat paid requests.
    """
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id,title,description,department FROM tasks "
            "WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return {"processed": False}
        task = dict(row)
        changed = db.execute(
            "UPDATE tasks SET status='running', worker_id=?, started_at=? "
            "WHERE id=? AND status='queued'",
            (worker_id, _now(), task["id"]),
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
        output = generate_text(prompt)
    except Exception as exc:
        with connect() as db:
            db.execute(
                "UPDATE tasks SET status='failed', error=?, finished_at=? WHERE id=?",
                (f"{type(exc).__name__}: {str(exc)[:1000]}", _now(), task["id"]),
            )
        raise
    with connect() as db:
        db.execute(
            "UPDATE tasks SET status='completed', result=?, error=NULL, finished_at=? WHERE id=?",
            (output, _now(), task["id"]),
        )
    return {"processed": True, "task_id": task["id"], "status": "completed"}
