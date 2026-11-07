"""Persistent desired-state and heartbeat records for the external worker service."""
from datetime import datetime, timedelta, timezone

from ai_os.db import connect


def _now():
    return datetime.now(timezone.utc).isoformat()


def set_worker_desired_state(state: str, actor: str) -> dict:
    if state not in {"running", "paused", "stopped"}:
        raise ValueError("Worker state must be running, paused, or stopped")
    now = _now()
    with connect() as db:
        db.execute(
            """UPDATE worker_control SET desired_state=?, updated_at=?, updated_by=?
               WHERE singleton_id=1""",
            (state, now, actor[:120]),
        )
        row = db.execute("SELECT * FROM worker_control WHERE singleton_id=1").fetchone()
    return dict(row)


def get_worker_desired_state() -> str:
    with connect() as db:
        row = db.execute(
            "SELECT desired_state FROM worker_control WHERE singleton_id=1"
        ).fetchone()
    return row["desired_state"] if row else "stopped"


def heartbeat_worker(worker_id: str, status: str, current_job_id: str | None = None) -> None:
    now = _now()
    with connect() as db:
        db.execute(
            """INSERT INTO worker_instances
               (worker_id,status,current_job_id,started_at,last_heartbeat,stopped_at)
               VALUES (?,?,?,?,?,NULL)
               ON CONFLICT(worker_id) DO UPDATE SET
                 status=excluded.status, current_job_id=excluded.current_job_id,
                 last_heartbeat=excluded.last_heartbeat,
                 stopped_at=CASE WHEN excluded.status='stopped' THEN excluded.last_heartbeat ELSE NULL END""",
            (worker_id, status, current_job_id, now, now),
        )


def get_worker_status(stale_after_seconds: int = 45) -> dict:
    now = datetime.now(timezone.utc)
    stale_before = (now - timedelta(seconds=stale_after_seconds)).isoformat()
    with connect() as db:
        control = db.execute(
            "SELECT desired_state,updated_at,updated_by FROM worker_control WHERE singleton_id=1"
        ).fetchone()
        rows = db.execute(
            "SELECT * FROM worker_instances ORDER BY last_heartbeat DESC"
        ).fetchall()
        counts = db.execute(
            """SELECT
                 SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
                 SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running,
                 SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
               FROM jobs"""
        ).fetchone()
    workers = []
    for row in rows:
        item = dict(row)
        item["healthy"] = item["last_heartbeat"] >= stale_before and item["status"] != "stopped"
        workers.append(item)
    active = [item for item in workers if item["healthy"]]
    return {
        "desired_state": control["desired_state"] if control else "stopped",
        "control_updated_at": control["updated_at"] if control else None,
        "control_updated_by": control["updated_by"] if control else "system",
        "process_running": bool(active),
        "active_workers": len(active),
        "workers": workers,
        "queue": {key: int(counts[key] or 0) for key in ("queued", "running", "failed")},
        "notice": "Worker control is persisted in the database. A separately hosted worker service must be running to act on start/resume requests.",
    }
