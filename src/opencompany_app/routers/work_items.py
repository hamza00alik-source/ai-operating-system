"""Owner-authenticated work-item creation and listing routes."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import BUSINESS_UNIT_IDS, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore
from opencompany_core.planning import PlanError, WorkPlan
from opencompany_core.organization import default_organization
from opencompany_app.api_schemas import WorkItemCreateInput
from opencompany_app.api_dependencies import get_store, require_owner_key, work_item_audit_record


router = APIRouter()


@router.get("/work-items", dependencies=[Depends(require_owner_key)])
def list_work_items(
    business_id: str | None = None, store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        items = store.list_work_items(business_id=business_id, limit=1000)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "count": len(items),
        "items": [
            {
                "id": str(item.id), "title": item.title, "objective": item.objective,
                "department": item.department, "business_id": item.business_id,
                "state": item.state.value,
                "assigned_agent_id": str(item.assigned_agent_id) if item.assigned_agent_id else None,
                "depends_on": [str(value) for value in item.depends_on],
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
    }


@router.post("/work-items", dependencies=[Depends(require_owner_key)])
def create_work_item(
    payload: WorkItemCreateInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        default_organization().get(payload.department)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    item = WorkItem(
        id=uuid4(), title=payload.title, objective=payload.objective,
        department=payload.department, state=TaskState.DRAFT,
        depends_on=payload.depends_on, business_id=payload.business_id,
    )
    # Resolve every dependency against the full company store before building
    # a business-scoped plan. Filtering first would make a cross-business
    # dependency look merely missing and hide the isolation violation.
    for dependency_id in payload.depends_on:
        prerequisite = store.get_work_item(dependency_id)
        if prerequisite is None:
            raise HTTPException(
                status_code=422,
                detail=f"Dependency {dependency_id} does not exist.",
            )
        if prerequisite.business_id != payload.business_id:
            raise HTTPException(
                status_code=422,
                detail="Work dependencies must belong to the same business unit.",
            )
    existing = store.list_work_items(business_id=payload.business_id, limit=1000)
    try:
        WorkPlan(tuple(existing) + (item,))
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save_work_item_with_audit(item, work_item_audit_record(item, "work_item.created"))
    return {"item_id": str(item.id), "state": item.state.value, "business_id": item.business_id}

