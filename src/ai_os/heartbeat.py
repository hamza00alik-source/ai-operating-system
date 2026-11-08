"""Persistent worker process heartbeat and freshness reporting."""
from datetime import datetime, timedelta, timezone

from ai_os.db import connect, initialize_database


def _now():
    return datetime.now(timezone.utc)


def record_worker_heartbeat(worker_id: str, status: str = "active") -> None:
    if status not in {"active", "stopped"}:
        raise ValueError("status must be active or stopped")
    now = _now().isoformat()
    initialize_database()
    with connect() as db:
        db.execute(
            """INSERT INTO worker_heartbeats(worker_id, status, started_at, last_seen_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(worker_id) DO UPDATE SET
                 status=excluded.status, last_seen_at=excluded.last_seen_at""",
            (worker_id, status, now, now),
        )


def get_worker_status(stale_after_seconds: int = 20) -> dict:
    initialize_database()
    with connect() as db:
        rows = db.execute(
            "SELECT worker_id, status, started_at, last_seen_at "
            "FROM worker_heartbeats ORDER BY last_seen_at DESC"
        ).fetchall()
    if not rows:
        return {"status": "never_seen", "workers": [], "stale_after_seconds": stale_after_seconds}
    now = _now()
    workers = []
    for row in rows:
        seen = datetime.fromisoformat(row["last_seen_at"])
        stale = now - seen > timedelta(seconds=stale_after_seconds)
        state = "stale" if row["status"] == "active" and stale else row["status"]
        workers.append({
            "worker_id": row["worker_id"], "status": state,
            "started_at": row["started_at"], "last_seen_at": row["last_seen_at"],
            "age_seconds": max(0, int((now - seen).total_seconds())),
        })
    overall = "active" if any(w["status"] == "active" for w in workers) else (
        "stale" if any(w["status"] == "stale" for w in workers) else "stopped"
    )
    return {"status": overall, "workers": workers, "stale_after_seconds": stale_after_seconds}
