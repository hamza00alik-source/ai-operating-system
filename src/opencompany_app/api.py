"""Standalone OpenCompany API, independent of legacy AIOS modules.

The service exposes a public read-only health check. All company records and
write operations require an owner API key. No endpoint invokes a model or
performs an external business action.
"""
from __future__ import annotations

import hmac
import os
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from opencompany_core.domain import AuditRecord, TaskState, WorkItem
from opencompany_core.lifecycle import StateTransitionError, transition_work_item
from opencompany_core.persistence import SQLiteStore
from opencompany_core.planning import PlanError, WorkPlan, action_requires_owner_approval
from opencompany_core.workforce import default_workforce
from opencompany_core.organization import default_organization
from opencompany_core.media_studio import video_capabilities
from opencompany_core.provider_catalog import free_provider_candidates


app = FastAPI(
    title="OpenCompany Core",
    version="0.2.0",
    description="Owner-authenticated API for OpenCompany's independently authored operating core.",
)


class PlanItemInput(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=12000)
    department: str = Field(min_length=1, max_length=80)
    state: TaskState = TaskState.READY
    depends_on: tuple[UUID, ...] = ()


class PlanPreviewInput(BaseModel):
    items: list[PlanItemInput] = Field(max_length=200)


class WorkItemCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=12000)
    department: str = Field(min_length=1, max_length=80)
    depends_on: tuple[UUID, ...] = ()


class WorkItemTransitionInput(BaseModel):
    target_state: TaskState


@lru_cache(maxsize=1)
def _default_store() -> SQLiteStore:
    database = os.environ.get("OPENCOMPANY_DATABASE_PATH", "data/opencompany_core.sqlite3")
    return SQLiteStore(database)


def get_store() -> SQLiteStore:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_store()


def require_owner_key(
    x_opencompany_api_key: str | None = Header(default=None),
) -> str:
    expected = os.environ.get("OPENCOMPANY_OWNER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    if not x_opencompany_api_key or not hmac.compare_digest(x_opencompany_api_key, expected):
        raise HTTPException(status_code=401, detail="Owner authentication failed.")
    return "owner"


def _record(item: WorkItem, action: str) -> AuditRecord:
    from datetime import datetime, timezone

    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type="work_item", subject_id=str(item.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={"state": item.state.value, "department": item.department},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "opencompany-core", "mode": "owner-authenticated"}


@app.get("/workforce/roles")
def workforce_roles() -> dict:
    roles = default_workforce().all()
    return {
        "catalogue": "opencompany-original",
        "count": len(roles),
        "roles": [
            {
                "key": role.key, "title": role.title, "function": role.function,
                "mission": role.mission, "capabilities": list(role.capabilities),
                "permitted_outputs": list(role.permitted_outputs),
                "prohibited_actions": list(role.prohibited_actions),
            }
            for role in roles
        ],
    }


@app.get("/organization/departments")
def organization_departments() -> dict:
    departments = default_organization().all()
    return {
        "catalogue": "opencompany-original",
        "count": len(departments),
        "departments": [
            {
                "key": item.key, "name": item.name, "mission": item.mission,
                "accountabilities": list(item.accountabilities),
                "manager_role_key": item.manager_role_key,
                "role_keys": list(item.role_keys),
                "decision_scope": list(item.decision_scope),
                "success_measures": list(item.success_measures),
                "approval_boundaries": list(item.approval_boundaries),
            }
            for item in departments
        ],
    }


@app.get("/media/capabilities")
def media_capabilities() -> dict:
    items = video_capabilities()
    return {
        "count": len(items),
        "capabilities": [
            {
                "key": item.key, "display_name": item.display_name,
                "state": item.state.value,
                "generation_modes": list(item.generation_modes),
                "execution_requirements": list(item.execution_requirements),
                "zero_budget_path": item.zero_budget_path,
                "safety_controls": list(item.safety_controls),
            }
            for item in items
        ],
    }


@app.get("/providers/candidates")
def provider_candidates() -> dict:
    items = free_provider_candidates()
    return {
        "gateway_enabled": False,
        "count": len(items),
        "candidates": [
            {
                "key": item.key, "display_name": item.display_name,
                "access_mode": item.access_mode,
                "current_free_evidence": item.current_free_evidence,
                "limits_or_conditions": list(item.limits_or_conditions),
                "activation_gate": item.activation_gate,
                "configured": False,
            }
            for item in items
        ],
    }


@app.post("/plans/preview")
def preview_plan(payload: PlanPreviewInput) -> dict:
    try:
        for candidate in payload.items:
            default_organization().get(candidate.department)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    items = tuple(
        WorkItem(
            id=item.id, title=item.title, objective=item.objective,
            department=item.department, state=item.state, depends_on=item.depends_on,
        )
        for item in payload.items
    )
    try:
        plan = WorkPlan(items)
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "item_count": len(items),
        "ready_item_ids": [str(item.id) for item in plan.ready_items()],
        "blocked_items": [
            {
                "id": str(item.id),
                "waiting_for": [
                    str(dependency) for dependency in item.depends_on
                    if plan.by_id[dependency].state != TaskState.COMPLETED
                ],
            }
            for item in plan.blocked_items()
        ],
        "execution_performed": False,
    }


@app.get("/policy/protected-actions")
def protected_actions() -> dict[str, list[str]]:
    actions = (
        "publish", "purchase", "pay", "send_customer_message",
        "make_customer_commitment", "change_production", "change_credentials",
        "deploy_production", "delete_customer_data",
    )
    return {
        "owner_approval_required": [
            action for action in actions if action_requires_owner_approval(action)
        ]
    }


@app.get("/work-items", dependencies=[Depends(require_owner_key)])
def list_work_items(store: SQLiteStore = Depends(get_store)) -> dict:
    items = store.list_work_items(limit=1000)
    return {
        "count": len(items),
        "items": [
            {
                "id": str(item.id), "title": item.title, "objective": item.objective,
                "department": item.department, "state": item.state.value,
                "depends_on": [str(value) for value in item.depends_on],
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
    }


@app.post("/work-items", dependencies=[Depends(require_owner_key)])
def create_work_item(
    payload: WorkItemCreateInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        default_organization().get(payload.department)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = WorkItem(
        id=uuid4(), title=payload.title, objective=payload.objective,
        department=payload.department, state=TaskState.DRAFT,
        depends_on=payload.depends_on,
    )
    existing = store.list_work_items(limit=1000)
    try:
        WorkPlan(tuple(existing) + (item,))
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save_work_item_with_audit(item, _record(item, "work_item.created"))
    return {"item_id": str(item.id), "state": item.state.value}


@app.post("/work-items/{item_id}/transition", dependencies=[Depends(require_owner_key)])
def change_work_item_state(
    item_id: UUID,
    payload: WorkItemTransitionInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    known = {value.id: value for value in store.list_work_items(limit=1000)}
    try:
        changed = transition_work_item(item, payload.target_state, known_items=known)
    except StateTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_work_item_with_audit(changed, _record(changed, "work_item.state_changed"))
    return {"item_id": str(changed.id), "state": changed.state.value}


@app.get("/audit/verify", dependencies=[Depends(require_owner_key)])
def verify_audit(store: SQLiteStore = Depends(get_store)) -> dict:
    return {
        "event_count": store.audit_event_count(),
        "chain_valid": store.verify_audit_chain(),
    }
