"""Shared runtime, persistence and owner-authentication dependencies.

This module owns the cached runtime singleton so API startup, shutdown and
route dependencies all continue to use the same process-local instance.
"""
from __future__ import annotations

import os

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from opencompany_core.domain import AgentState, AuditRecord, WorkItem
from opencompany_core.organization import default_organization
from opencompany_core.workforce import default_workforce
from opencompany_core.worker_queue import QueueError
from opencompany_app.auth_dependencies import require_owner_key, _login_retry_after, _clear_login_failures
from opencompany_app.runtime_dependencies import (
    OpenCompanyRuntime, _default_runtime, get_runtime, get_optional_runtime,
    get_delegation_store, get_store,
)


from opencompany_core.domain import AgentState, AuditRecord, WorkItem
from opencompany_core.organization import default_organization
from opencompany_core.workforce import default_workforce
from opencompany_core.worker_queue import QueueError


def work_item_audit_record(item: WorkItem, action: str) -> AuditRecord:
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type="work_item", subject_id=str(item.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={
            "state": item.state.value, "department": item.department,
            "business_id": item.business_id,
        },
    )

def _auto_queue_approved_work_enabled() -> bool:
    return os.environ.get("OPENCOMPANY_AUTO_QUEUE_APPROVED_WORK", "false").strip().casefold() in {"1", "true", "yes", "on"}


def _free_provider_ready(runtime: OpenCompanyRuntime) -> bool:
    return bool(runtime.gateway.eligible_providers(request_budget_usd=0.0))


def _auto_queue_task(runtime: OpenCompanyRuntime, task: WorkItem, agent, *, action: str) -> None:
    from datetime import datetime, timezone

    if agent is None or agent.state != AgentState.ACTIVE or agent.department != task.department:
        raise QueueError("automatic queueing requires an active assignee in the task department")
    department = default_organization().get(task.department)
    role = default_workforce().get(agent.role_key)
    expected_team = (
        "executive" if agent.role_key == "chief_executive_orchestrator"
        else "management" if agent.role_key == department.manager_role_key
        else role.team_key
    )
    if agent.role_key not in department.role_keys or agent.team_key != expected_team:
        raise QueueError("automatic queueing rejected an unverified role/team assignment")
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="system", actor_id="opencompany-auto-queue",
        action=action, subject_type="work_item", subject_id=str(task.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={"agent_id": str(agent.id), "role_key": agent.role_key,
                 "team_key": agent.team_key, "business_id": task.business_id,
                 "request_budget_usd": 0.0},
    )
    runtime.queue.enqueue_authorized(
        task, agent.id, {"role_key": agent.role_key, "team_key": agent.team_key}, event,
    )

