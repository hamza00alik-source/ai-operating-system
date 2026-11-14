"""Trusted server-side persistence for agent-originated approval intents."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from .domain import AgentState, AuditRecord, TaskState
from .persistence import SQLiteStore

_ALLOWED_ACTIONS = frozenset({
    "publish_listing", "send_customer_message", "make_customer_commitment",
    "purchase", "payment", "production_change", "credential_change",
    "account_change", "deploy_production", "delete_customer_data", "other",
})


def _ensure_approval_table(store: SQLiteStore) -> None:
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


def record_agent_approval_requests(
    store: SQLiteStore, agent_id: UUID, item, requests: list[dict], *, allowed_states=None
) -> list[dict]:
    """Persist model-originated approval intents using trusted worker identity."""
    agent = store.get_agent(agent_id)
    current_item = store.get_work_item(item.id)
    permitted_states = allowed_states or {TaskState.IN_PROGRESS}
    if agent is None or agent.state != AgentState.ACTIVE:
        raise ValueError("requesting agent is not active")
    if (current_item is None or current_item.business_id != item.business_id
            or current_item.assigned_agent_id != agent.id
            or current_item.state not in permitted_states):
        raise ValueError("agent is not the active assignee of the permitted work item")
    _ensure_approval_table(store)
    recorded = []
    for index, request in enumerate(requests):
        action = request["action_type"]
        if action not in _ALLOWED_ACTIONS:
            continue
        amount, currency = request.get("estimated_amount_minor"), request.get("currency")
        if (amount is None) != (currency is None):
            continue
        if currency and (not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha()):
            continue
        request_id = str(uuid5(
            NAMESPACE_URL,
            f"opencompany:agent-approval:{item.id}:{index}:{json.dumps(request, sort_keys=True)}",
        ))
        now = datetime.now(timezone.utc)
        requested_by = f"agent:{agent.id}:role:{agent.role_key}:work_item:{item.id}"
        with store._lock:
            exists = store._connection.execute(
                "SELECT id FROM external_action_approvals WHERE id=?", (request_id,)
            ).fetchone()
            if exists is None:
                store._connection.execute(
                    """INSERT INTO external_action_approvals
                       (id,business_id,action_type,title,description,target_reference,requested_by,
                        estimated_amount_minor,currency,status,requested_at)
                       VALUES(?,?,?,?,?,?,?,?,?,'pending',?)""",
                    (request_id, item.business_id, action, request["title"].strip(),
                     request["description"].strip(), request.get("target_reference"), requested_by,
                     amount, currency.upper() if currency else None, now.isoformat()),
                )
                store.append_audit_record(AuditRecord(
                    id=uuid4(), occurred_at=now, actor_type="agent", actor_id=str(agent.id),
                    action="external_approval.agent_requested",
                    subject_type="external_action_approval", subject_id=request_id,
                    outcome="pending", correlation_id=str(item.id),
                    details={"business_id": item.business_id, "action_type": action,
                             "work_item_id": str(item.id), "role_key": agent.role_key,
                             "execution_performed": False},
                ))
        recorded.append({"request_id": request_id, "status": "pending",
                         "execution_performed": False})
    return recorded
