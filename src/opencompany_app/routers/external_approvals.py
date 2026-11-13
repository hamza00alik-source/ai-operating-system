"""Owner-gated registry for external-action authorization requests.

This module records decisions only. It deliberately has no executor, connector,
payment client, publisher, messaging client, or production mutation capability.
An authorized request must still be implemented and executed by a separately
reviewed action-specific adapter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from opencompany_core.domain import BUSINESS_UNIT_IDS, AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_app.api_dependencies import get_store, require_owner_key

router = APIRouter()
ACTION_TYPES = frozenset({
    "publish_listing", "send_customer_message", "make_customer_commitment",
    "purchase", "payment", "production_change", "credential_change",
    "account_change", "deploy_production", "delete_customer_data", "other",
})
DECISIONS = frozenset({"approve", "reject"})


class ExternalApprovalCreateInput(BaseModel):
    business_id: str
    action_type: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    target_reference: str | None = Field(default=None, max_length=500)
    requested_by: str = Field(default="owner", min_length=1, max_length=120)
    # Deliberately no credentials, payment instruments, or arbitrary payload.
    estimated_amount_minor: int | None = Field(default=None, ge=0, le=9_000_000_000_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class ExternalApprovalDecisionInput(BaseModel):
    decision: str
    rationale: str = Field(min_length=1, max_length=2000)
    confirm_action: str = Field(default="", max_length=40)


def _ensure_table(store: SQLiteStore) -> None:
    with store._lock:
        store._connection.execute("""
            CREATE TABLE IF NOT EXISTS external_action_approvals (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL CHECK(business_id IN
                    ('core','physical-agency','physical-brand','digital-products')),
                action_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                target_reference TEXT,
                requested_by TEXT NOT NULL,
                estimated_amount_minor INTEGER,
                currency TEXT,
                status TEXT NOT NULL CHECK(status IN
                    ('pending','authorized_not_executed','rejected','cancelled','expired')),
                requested_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                rationale TEXT,
                expires_at TEXT
            )
        """)
        store._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_external_approval_scope_status "
            "ON external_action_approvals(business_id,status,requested_at)"
        )


def _serialize(row) -> dict:
    return {key: row[key] for key in row.keys()}


@router.post("/external-approvals", dependencies=[Depends(require_owner_key)])
def create_external_approval(
    payload: ExternalApprovalCreateInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    if payload.business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    if payload.action_type not in ACTION_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported external action type.")
    if (payload.estimated_amount_minor is None) != (payload.currency is None):
        raise HTTPException(status_code=422, detail="Amount and currency must be supplied together.")
    if payload.currency and not payload.currency.isalpha():
        raise HTTPException(status_code=422, detail="Currency must be a three-letter code.")
    _ensure_table(store)
    now = datetime.now(timezone.utc)
    request_id = str(uuid4())
    with store._lock:
        store._connection.execute(
            """INSERT INTO external_action_approvals
               (id,business_id,action_type,title,description,target_reference,requested_by,
                estimated_amount_minor,currency,status,requested_at)
               VALUES(?,?,?,?,?,?,?,?,?,'pending',?)""",
            (request_id, payload.business_id, payload.action_type, payload.title.strip(),
             payload.description.strip(), payload.target_reference, payload.requested_by.strip(),
             payload.estimated_amount_minor, payload.currency.upper() if payload.currency else None,
             now.isoformat()),
        )
    store.append_audit_record(AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="external_approval.requested", subject_type="external_action_approval",
        subject_id=request_id, outcome="pending", correlation_id=str(uuid4()),
        details={"business_id": payload.business_id, "action_type": payload.action_type},
    ))
    return {"request_id": request_id, "status": "pending", "execution_performed": False}


@router.get("/external-approvals", dependencies=[Depends(require_owner_key)])
def list_external_approvals(
    business_id: str | None = None,
    status: str | None = None,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    if status is not None and status not in {"pending","authorized_not_executed","rejected","cancelled","expired"}:
        raise HTTPException(status_code=422, detail="Unknown approval status.")
    _ensure_table(store)
    clauses, values = [], []
    if business_id is not None:
        clauses.append("business_id=?"); values.append(business_id)
    if status is not None:
        clauses.append("status=?"); values.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with store._lock:
        rows = store._connection.execute(
            "SELECT * FROM external_action_approvals" + where + " ORDER BY requested_at DESC LIMIT 200",
            tuple(values),
        ).fetchall()
    return {"count": len(rows), "requests": [_serialize(row) for row in rows],
            "execution_supported": False}


@router.post("/external-approvals/{request_id}/decision", dependencies=[Depends(require_owner_key)])
def decide_external_approval(
    request_id: UUID,
    payload: ExternalApprovalDecisionInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    if payload.decision not in DECISIONS:
        raise HTTPException(status_code=422, detail="Decision must be approve or reject.")
    if payload.decision == "approve" and payload.confirm_action != "AUTHORIZE":
        raise HTTPException(status_code=422, detail="Type AUTHORIZE to record this external-action authorization.")
    _ensure_table(store)
    now = datetime.now(timezone.utc)
    status = "authorized_not_executed" if payload.decision == "approve" else "rejected"
    with store._lock:
        row = store._connection.execute(
            "SELECT * FROM external_action_approvals WHERE id=?", (str(request_id),)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="External-action request not found.")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Only pending requests can receive a decision.")
        expires = (now + timedelta(hours=24)).isoformat() if payload.decision == "approve" else None
        store._connection.execute(
            """UPDATE external_action_approvals
               SET status=?,decided_at=?,decided_by='owner',rationale=?,expires_at=?
               WHERE id=? AND status='pending'""",
            (status, now.isoformat(), payload.rationale.strip(), expires, str(request_id)),
        )
    store.append_audit_record(AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="external_approval." + payload.decision,
        subject_type="external_action_approval", subject_id=str(request_id),
        outcome=status, correlation_id=str(uuid4()),
        details={"action_type": row["action_type"], "business_id": row["business_id"],
                 "execution_performed": False},
    ))
    return {"request_id": str(request_id), "status": status,
            "execution_performed": False,
            "message": "Authorization recorded only; no external action was executed."}


@router.post("/external-approvals/{request_id}/cancel", dependencies=[Depends(require_owner_key)])
def cancel_external_approval(
    request_id: UUID,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    _ensure_table(store)
    now = datetime.now(timezone.utc)
    with store._lock:
        row = store._connection.execute(
            "SELECT * FROM external_action_approvals WHERE id=?", (str(request_id),)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="External-action request not found.")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Only pending requests can be cancelled.")
        store._connection.execute(
            "UPDATE external_action_approvals SET status='cancelled',decided_at=?,decided_by='owner' WHERE id=?",
            (now.isoformat(), str(request_id)),
        )
    store.append_audit_record(AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="external_approval.cancelled", subject_type="external_action_approval",
        subject_id=str(request_id), outcome="cancelled", correlation_id=str(uuid4()),
        details={"business_id": row["business_id"], "action_type": row["action_type"]},
    ))
    return {"request_id": str(request_id), "status": "cancelled", "execution_performed": False}
