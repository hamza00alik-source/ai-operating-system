"""Deterministic executive supervision and escalation for AIOS.

This supervisor monitors persisted work across isolated business environments,
records actionable alerts, and never retries work or performs external actions.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.brain import BUSINESS_IDS
from ai_os.db import connect, initialize_database
from ai_os.workflows import initialize_workflows

logger = logging.getLogger("ai_os.executive_supervisor")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(db, name: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def executive_status(business_id: str | None = None) -> dict:
    """Return isolated operational metrics and open escalations."""
    if business_id is not None and business_id not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    initialize_database()
    initialize_workflows()
    selected = [business_id] if business_id else sorted(BUSINESS_IDS)
    result = []
    with connect() as db:
        for scope in selected:
            task_rows = db.execute(
                "SELECT status,COUNT(*) AS count FROM tasks WHERE business_id=? GROUP BY status",
                (scope,),
            ).fetchall()
            run_rows = db.execute(
                """SELECT r.status,COUNT(*) AS count FROM agent_runs r
                   JOIN tasks t ON t.id=r.task_id WHERE t.business_id=? GROUP BY r.status""",
                (scope,),
            ).fetchall()
            workflow_rows = db.execute(
                "SELECT status,COUNT(*) AS count FROM workflow_instances WHERE business_id=? GROUP BY status",
                (scope,),
            ).fetchall()
            approval_count = db.execute(
                "SELECT COUNT(*) AS count FROM approvals WHERE business_id=? AND status='pending'",
                (scope,),
            ).fetchone()["count"]
            inbox_failed = 0
            if _table_exists(db, "department_inbox_processing"):
                inbox_failed = db.execute(
                    "SELECT COUNT(*) AS count FROM department_inbox_processing WHERE business_id=? AND status='failed'",
                    (scope,),
                ).fetchone()["count"]
            alerts = []
            if _table_exists(db, "executive_alerts"):
                alerts = [dict(row) for row in db.execute(
                    """SELECT id,category,severity,title,details,status,created_at,updated_at
                       FROM executive_alerts WHERE business_id=? AND status='open'
                       ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
                       created_at DESC LIMIT 50""", (scope,)
                ).fetchall()]
            result.append({
                "business_id": scope,
                "tasks": {row["status"]: row["count"] for row in task_rows},
                "agent_runs": {row["status"]: row["count"] for row in run_rows},
                "workflows": {row["status"]: row["count"] for row in workflow_rows},
                "pending_owner_approvals": approval_count,
                "failed_department_inbox_messages": inbox_failed,
                "open_alert_count": len(alerts),
                "open_alerts": alerts,
            })
    return {
        "supervisor": "deterministic-executive-supervisor",
        "businesses": result,
        "policy": {
            "business_isolation": "strict",
            "automatic_retry": False,
            "external_actions": False,
            "owner_approval_required_for": [
                "publishing", "customer_contact", "customer_commitments",
                "payments", "purchases", "account_changes", "production_release"
            ],
        },
    }


def supervise_once() -> dict:
    """Reconcile current failures/blockers into idempotent executive alerts."""
    initialize_database()
    initialize_workflows()
    now = _now()
    created = updated = resolved = 0
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS executive_alerts (
                id TEXT PRIMARY KEY,
                alert_key TEXT NOT NULL UNIQUE,
                business_id TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)
        active = {}
        failed_runs = db.execute("""
            SELECT r.id,r.error,r.status,t.business_id,t.title,t.department
            FROM agent_runs r JOIN tasks t ON t.id=r.task_id
            WHERE r.status IN ('failed','partial')
        """).fetchall()
        for row in failed_runs:
            key = "run:" + row["id"]
            active[key] = (row["business_id"], "execution", "high",
                "Agent run needs executive review",
                f"{row['department']} · {row['title']} · {row['status']}: {row['error'] or 'No error detail'}"[:2000])
        blocked = db.execute("""
            SELECT w.id,w.business_id,w.name,s.title,s.department,t.status AS task_status
            FROM workflow_instances w
            LEFT JOIN workflow_steps s ON s.workflow_id=w.id AND s.status IN ('failed','blocked')
            LEFT JOIN tasks t ON t.id=s.task_id
            WHERE w.status='blocked'
        """).fetchall()
        for row in blocked:
            key = "workflow:" + row["id"]
            active[key] = (row["business_id"], "workflow", "high",
                "Department workflow is blocked",
                f"{row['name']} · blocked step: {row['department'] or 'unknown'} · {row['title'] or 'No step detail'}")
        if _table_exists(db, "department_inbox_processing"):
            failed_messages = db.execute("""
                SELECT message_id,business_id,department,error FROM department_inbox_processing
                WHERE status='failed'
            """).fetchall()
            for row in failed_messages:
                key = "inbox:" + row["message_id"]
                active[key] = (row["business_id"], "department_inbox", "medium",
                    "Department inbox message needs review",
                    f"{row['department']}: {row['error'] or 'Interpretation failed'}"[:1000])
        for key, (scope, category, severity, title, details) in active.items():
            existing = db.execute("SELECT id,status FROM executive_alerts WHERE alert_key=?", (key,)).fetchone()
            if existing:
                db.execute("""
                    UPDATE executive_alerts SET business_id=?,category=?,severity=?,title=?,
                    details=?,status='open',updated_at=?,resolved_at=NULL WHERE alert_key=?
                """, (scope, category, severity, title, details, now, key))
                if existing["status"] != "open":
                    updated += 1
            else:
                db.execute("""
                    INSERT INTO executive_alerts
                    (id,alert_key,business_id,category,severity,title,details,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,'open',?,?)
                """, (str(uuid4()), key, scope, category, severity, title, details, now, now))
                created += 1
        open_rows = db.execute("SELECT alert_key FROM executive_alerts WHERE status='open'").fetchall()
        active_keys = set(active)
        for row in open_rows:
            if row["alert_key"] not in active_keys:
                db.execute("""
                    UPDATE executive_alerts SET status='resolved',updated_at=?,resolved_at=?
                    WHERE alert_key=? AND status='open'
                """, (now, now, row["alert_key"]))
                resolved += 1
    return {"alerts_created": created, "alerts_reopened": updated,
            "alerts_resolved": resolved, "active_conditions": len(active),
            "status": executive_status()}


def executive_supervisor_loop(stop_event, poll_seconds: int = 15) -> None:
    """Continuously reconcile failures and blockers without retrying or taking side effects."""
    delay = max(5, min(int(poll_seconds), 120))
    while not stop_event.is_set():
        try:
            supervise_once()
        except Exception:
            logger.exception("Executive supervisor recovered from an error")
        stop_event.wait(delay)
