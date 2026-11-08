"""Task and approval business logic."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.schemas import ApprovalCreate, ApprovalDecision, TaskCreate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_action(action: str, actor_id: str, resource_id: str, payload: dict) -> tuple[str, str]:
    document = {
        "action": action,
        "actor_id": actor_id,
        "resource_id": resource_id,
        "payload": payload,
    }
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    payload_json = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )
    return payload_json, fingerprint


def create_task(payload: TaskCreate) -> dict:
    task = {
        "id": str(uuid4()), "title": payload.title,
        "description": payload.description, "department": payload.department,
        "status": "queued", "created_at": _now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO tasks
            (id,title,description,department,status,created_at)
            VALUES (:id,:title,:description,:department,:status,:created_at)""",
            task,
        )
    return task


def list_tasks() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def _approval_dict(row) -> dict:
    result = dict(row)
    raw_payload = result.get("action_payload_json")
    result["action_payload"] = json.loads(raw_payload) if raw_payload else None
    result.pop("action_payload_json", None)
    return result


def create_approval(payload: ApprovalCreate) -> dict:
    if payload.task_id:
        with connect() as db:
            exists = db.execute(
                "SELECT 1 FROM tasks WHERE id=?", (payload.task_id,)
            ).fetchone()
        if not exists:
            raise LookupError("Task not found")

    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    expires_at = (now + timedelta(seconds=payload.expires_in_seconds)).isoformat()
    payload_json, fingerprint = _canonical_action(
        payload.action, payload.actor_id, payload.resource_id, payload.action_payload
    )
    approval = {
        "id": str(uuid4()), "task_id": payload.task_id,
        "action": payload.action, "details": payload.details,
        "actor_id": payload.actor_id, "resource_id": payload.resource_id,
        "action_payload_json": payload_json, "action_fingerprint": fingerprint,
        "status": "pending", "created_at": created_at,
        "decided_at": None, "expires_at": expires_at, "consumed_at": None,
    }
    with connect() as db:
        db.execute(
            """INSERT INTO approvals
            (id,task_id,action,details,actor_id,resource_id,action_payload_json,
             action_fingerprint,status,created_at,decided_at,expires_at,consumed_at)
            VALUES (:id,:task_id,:action,:details,:actor_id,:resource_id,
                    :action_payload_json,:action_fingerprint,:status,:created_at,
                    :decided_at,:expires_at,:consumed_at)""",
            approval,
        )
    return _approval_dict(approval)


def list_approvals() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM approvals ORDER BY created_at DESC").fetchall()
    return [_approval_dict(row) for row in rows]


def decide_approval(approval_id: str, payload: ApprovalDecision) -> dict | None:
    decided_at = _now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "pending":
            raise ValueError("This approval request has already been decided")
        expires_at = row["expires_at"]
        if expires_at and expires_at <= decided_at:
            db.execute(
                "UPDATE approvals SET status='expired' WHERE id=? AND status='pending'",
                (approval_id,),
            )
            raise ValueError("This approval request has expired")
        changed = db.execute(
            "UPDATE approvals SET status=?, decided_at=? "
            "WHERE id=? AND status='pending' AND (expires_at IS NULL OR expires_at>?)",
            (payload.decision, decided_at, approval_id, decided_at),
        ).rowcount
        if changed != 1:
            raise ValueError("This approval request is no longer pending or has expired")
        updated = db.execute(
            "SELECT * FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
    return _approval_dict(updated)


def consume_approval(
    approval_id: str, *, actor_id: str, action: str,
    resource_id: str, action_payload: dict,
) -> dict | None:
    """Atomically consume a matching approved action immediately before execution.

    This function authorizes one matching execution attempt; it does not perform
    the external action. Callers must invoke it immediately before their executor.
    """
    _, fingerprint = _canonical_action(action, actor_id, resource_id, action_payload)
    now = _now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "approved" or row["consumed_at"] is not None:
            raise ValueError("Approval is not approved or has already been consumed")
        if not row["expires_at"] or row["expires_at"] <= now:
            db.execute(
                "UPDATE approvals SET status='expired' WHERE id=? AND status='approved'",
                (approval_id,),
            )
            raise ValueError("Approval has expired")
        if not row["action_fingerprint"] or not hmac.compare_digest(
            row["action_fingerprint"], fingerprint
        ):
            raise ValueError("Proposed action does not match the approved action")
        changed = db.execute(
            """UPDATE approvals SET status='consumed', consumed_at=?
            WHERE id=? AND status='approved' AND consumed_at IS NULL
              AND action_fingerprint=? AND actor_id=? AND resource_id=?
              AND expires_at>?""",
            (now, approval_id, fingerprint, actor_id, resource_id, now),
        ).rowcount
        if changed != 1:
            raise ValueError("Approval could not be consumed; state changed")
        consumed = db.execute(
            "SELECT * FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
    return _approval_dict(consumed)
