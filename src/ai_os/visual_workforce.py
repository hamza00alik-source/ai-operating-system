"""Read-only presentation data for the optional 3D workforce client.

The workflow currently has three durable role slots, not a general-purpose
registry of independently provisioned agents. This module exposes only those
role identities and derives presence from persisted worker/task records.
"""
from datetime import datetime, timezone

from ai_os.agent_runtime import AGENT_STEPS
from ai_os.db import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_visual_workforce() -> dict:
    """Return a redacted, read-only snapshot; never infer activity from absence."""
    now = _now()
    with connect() as db:
        task_rows = db.execute(
            """SELECT department, status, COUNT(*) AS count
               FROM tasks GROUP BY department, status
               ORDER BY department, status"""
        ).fetchall()
        latest_rows = db.execute(
            """SELECT s.step_key, s.agent_name, s.status AS step_status,
                      s.started_at, s.finished_at, s.worker_id,
                      t.id AS task_id, t.department, t.status AS task_status,
                      t.lease_expires_at
               FROM agent_steps AS s
               JOIN tasks AS t ON t.id = s.task_id
               JOIN (
                   SELECT step_key, MAX(id) AS latest_id
                   FROM agent_steps GROUP BY step_key
               ) AS latest ON latest.latest_id = s.id"""
        ).fetchall()
        active_rows = db.execute(
            """SELECT s.step_key, s.agent_name, s.started_at, s.worker_id,
                      t.id AS task_id, t.department, t.lease_expires_at
               FROM agent_steps AS s
               JOIN tasks AS t ON t.id = s.task_id
               WHERE s.status='running' AND t.status='running'
                 AND t.lease_expires_at IS NOT NULL
                 AND t.lease_expires_at > ?""",
            (now,),
        ).fetchall()

    latest_by_key = {row["step_key"]: dict(row) for row in latest_rows}
    active_by_key = {}
    for row in active_rows:
        active_by_key.setdefault(row["step_key"], []).append(dict(row))

    agents = []
    for step_key, display_name, _instructions in AGENT_STEPS:
        active = active_by_key.get(step_key, [])
        latest = latest_by_key.get(step_key)
        if active:
            # Multiple concurrent workflow tasks can use the same role slot.
            agents.append({
                "agent_id": f"workflow:{step_key}",
                "display_name": display_name,
                "role_key": step_key,
                "department": active[0]["department"],
                "presence": "working",
                "presence_source": "active_step_and_unexpired_task_lease",
                "observed_at": max(item["started_at"] for item in active),
                "active_task_ids": [item["task_id"] for item in active],
            })
        elif latest and (latest["step_status"] == "failed" or latest["task_status"] in {"failed", "blocked"}):
            agents.append({
                "agent_id": f"workflow:{step_key}",
                "display_name": display_name,
                "role_key": step_key,
                "department": latest["department"],
                "presence": "attention",
                "presence_source": "persisted_failed_or_blocked_step",
                "observed_at": latest["finished_at"] or latest["started_at"],
                "active_task_ids": [],
            })
        elif latest and latest["step_status"] == "completed":
            agents.append({
                "agent_id": f"workflow:{step_key}",
                "display_name": display_name,
                "role_key": step_key,
                "department": latest["department"],
                "presence": "completed",
                "presence_source": "persisted_completed_step",
                "observed_at": latest["finished_at"] or latest["started_at"],
                "active_task_ids": [],
            })
        else:
            agents.append({
                "agent_id": f"workflow:{step_key}",
                "display_name": display_name,
                "role_key": step_key,
                "department": None,
                "presence": "unknown",
                "presence_source": "no_verified_step_record",
                "observed_at": None,
                "active_task_ids": [],
            })

    department_counts = {}
    for row in task_rows:
        department = row["department"]
        item = department_counts.setdefault(
            department,
            {"department": department, "task_count": 0, "by_status": {}},
        )
        item["task_count"] += row["count"]
        item["by_status"][row["status"]] = row["count"]

    return {
        "generated_at": now,
        "mode": "read_only",
        "agent_registry_scope": "three_persisted_workflow_role_slots",
        "agents": agents,
        "departments": list(department_counts.values()),
    }
