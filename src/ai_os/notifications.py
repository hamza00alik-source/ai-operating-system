"""Owner-gated notification queue with optional, explicitly enabled Apprise delivery.

No notification is sent when an item is enqueued or approved. Delivery must be
invoked explicitly by an owner-operated worker/API action after configuration.
"""
from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                audience TEXT NOT NULL CHECK(audience IN ('internal','customer')),
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                approval_id TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_status_created "
            "ON notifications(status, created_at)"
        )


def enqueue_notification(*, title: str, body: str, audience: str = "internal",
                         approval_id: str | None = None) -> dict:
    """Persist an intent only; customer-facing messages always start pending approval."""
    if audience not in {"internal", "customer"}:
        raise ValueError("Audience must be 'internal' or 'customer'.")
    title, body = title.strip(), body.strip()
    if not title or not body:
        raise ValueError("Notification title and body are required.")
    if len(title) > 180 or len(body) > 8000:
        raise ValueError("Notification content exceeds the allowed length.")
    if audience == "customer" and not approval_id:
        raise ValueError("Customer notifications require an owner approval record.")
    _ensure_schema()
    now, notification_id = _now(), str(uuid4())
    status = "pending_approval" if audience == "customer" else "queued"
    with connect() as db:
        db.execute(
            """INSERT INTO notifications
               (id,audience,title,body,approval_id,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (notification_id, audience, title, body, approval_id, status, now, now),
        )
        row = db.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
    return dict(row)


def approve_notification(notification_id: str) -> dict:
    """Release a customer notification only when its linked owner approval is approved."""
    _ensure_schema()
    with connect() as db:
        row = db.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
        if row is None:
            raise LookupError("Notification not found.")
        if row["audience"] != "customer":
            raise ValueError("Only customer notifications require this approval transition.")
        approval = db.execute(
            "SELECT status FROM approvals WHERE id=?", (row["approval_id"],)
        ).fetchone()
        if approval is None or approval["status"] != "approved":
            raise PermissionError("The linked owner approval is not approved.")
        if row["status"] != "pending_approval":
            raise ValueError("Notification is not awaiting approval.")
        db.execute(
            "UPDATE notifications SET status='queued',updated_at=? WHERE id=?",
            (_now(), notification_id),
        )
        updated = db.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
    return dict(updated)


def list_notifications(*, limit: int = 50) -> list[dict]:
    _ensure_schema()
    limit = max(1, min(int(limit), 200))
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def deliver_notification(notification_id: str) -> dict:
    """Explicitly deliver one queued item; disabled by default and never auto-called."""
    _ensure_schema()
    if os.getenv("AI_OS_NOTIFICATIONS_ENABLED", "").strip().lower() != "true":
        raise PermissionError("Notifications are disabled. Owner configuration is required.")
    destination = os.getenv("AI_OS_APPRISE_URL", "").strip()
    if not destination:
        raise PermissionError("No Apprise destination is configured.")
    with connect() as db:
        row = db.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
        if row is None:
            raise LookupError("Notification not found.")
        if row["status"] != "queued":
            raise PermissionError("Only queued notifications can be delivered.")
        if row["audience"] == "customer":
            approval = db.execute(
                "SELECT status FROM approvals WHERE id=?", (row["approval_id"],)
            ).fetchone()
            if approval is None or approval["status"] != "approved":
                raise PermissionError("Customer notification approval is missing or no longer approved.")
        # Atomically claim the item before the external call to prevent two
        # owner-triggered workers from sending the same notification twice.
        claimed = db.execute(
            "UPDATE notifications SET status='sending',updated_at=? WHERE id=? AND status='queued'",
            (_now(), notification_id),
        ).rowcount
        if not claimed:
            raise PermissionError("Notification was already claimed by another delivery attempt.")
    try:
        apprise_module = importlib.import_module("apprise")
    except ImportError as exc:
        with connect() as db:
            db.execute(
                "UPDATE notifications SET status='queued',updated_at=? WHERE id=? AND status='sending'",
                (_now(), notification_id),
            )
        raise RuntimeError(
            "Optional Apprise package is not installed. Core AIOS remains dependency-free."
        ) from exc
    notifier = apprise_module.Apprise()
    if not notifier.add(destination):
        with connect() as db:
            db.execute(
                "UPDATE notifications SET status='failed',last_error=?,updated_at=? WHERE id=? AND status='sending'",
                ("Apprise rejected the configured destination.", _now(), notification_id),
            )
        raise ValueError("Apprise rejected the configured destination.")
    try:
        delivered = bool(notifier.notify(title=row["title"], body=row["body"]))
    except Exception as exc:
        with connect() as db:
            db.execute(
                "UPDATE notifications SET status='failed',attempts=attempts+1,last_error=?,updated_at=? WHERE id=? AND status='sending'",
                (str(exc)[:500], _now(), notification_id),
            )
        raise
    now = _now()
    with connect() as db:
        if delivered:
            db.execute(
                "UPDATE notifications SET status='sent',attempts=attempts+1,last_error=NULL,updated_at=? WHERE id=? AND status='sending'",
                (now, notification_id),
            )
        else:
            db.execute(
                "UPDATE notifications SET status='failed',attempts=attempts+1,last_error=?,updated_at=? WHERE id=? AND status='sending'",
                ("Apprise did not confirm delivery.", now, notification_id),
            )
        updated = db.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
    return dict(updated)
