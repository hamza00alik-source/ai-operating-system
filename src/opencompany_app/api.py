"""Standalone, read-only API for the independently authored OpenCompany core.

This application is intentionally separate from the legacy AIOS service while
the latter undergoes provenance review. It exposes no model, filesystem, shell,
credential, payment, publishing, or production-control endpoints.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from opencompany_core.domain import TaskState, WorkItem
from opencompany_core.planning import (
    PlanError, WorkPlan, action_requires_owner_approval,
)
from opencompany_core.workforce import default_workforce


app = FastAPI(
    title="OpenCompany Core",
    version="0.1.0",
    description="Read-only preview API for OpenCompany's independently authored operating core.",
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "opencompany-core", "mode": "read-only"}


@app.get("/workforce/roles")
def workforce_roles() -> dict:
    roles = default_workforce().all()
    return {
        "catalogue": "opencompany-original",
        "count": len(roles),
        "roles": [
            {
                "key": role.key,
                "title": role.title,
                "function": role.function,
                "mission": role.mission,
                "capabilities": list(role.capabilities),
                "permitted_outputs": list(role.permitted_outputs),
                "prohibited_actions": list(role.prohibited_actions),
            }
            for role in roles
        ],
    }


@app.post("/plans/preview")
def preview_plan(payload: PlanPreviewInput) -> dict:
    items = tuple(
        WorkItem(
            id=item.id,
            title=item.title,
            objective=item.objective,
            department=item.department,
            state=item.state,
            depends_on=item.depends_on,
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
                    str(dependency)
                    for dependency in item.depends_on
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
