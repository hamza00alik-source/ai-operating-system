"""Small database-backed scheduler for durable worker tasks.

This first runtime schedules queued task records and recovers expired leases.
Multi-agent step graphs are deliberately layered on top later.
"""
from datetime import datetime, timedelta, timezone

from ai_os.db import connect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def schedule_ready_steps() -> dict:
    """Recover tasks whose worker lease expired; never duplicate a live lease."""
    now = _now()
    now_text = now.isoformat()
    recovered = 0
    failed = 0
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        stale = db.execute(
            """SELECT id, attempts, max_attempts FROM tasks
               WHERE status='running' AND lease_expires_at IS NOT NULL
               AND lease_expires_at < ?""",
            (now_text,),
        ).fetchall()
        for task in stale:
            if task["attempts"] < task["max_attempts"]:
                db.execute(
                    """UPDATE tasks SET status='queued', worker_id=NULL,
                       lease_expires_at=NULL, error='Worker lease expired; task requeued'
                       WHERE id=? AND status='running'""",
                    (task["id"],),
                )
                recovered += 1
            else:
                db.execute(
                    """UPDATE tasks SET status='failed', worker_id=NULL,
                       lease_expires_at=NULL, completed_at=?,
                       error='Worker lease expired; retry limit reached'
                       WHERE id=? AND status='running'""",
                    (now_text, task["id"]),
                )
                failed += 1
    return {"scheduled": recovered, "recovered": recovered, "failed": failed}
