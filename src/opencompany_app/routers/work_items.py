"""Owner-authenticated work-item creation and listing routes."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import BUSINESS_UNIT_IDS, AuditRecord, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore
from opencompany_core.planning import PlanError, WorkPlan
from opencompany_core.organization import default_organization
from opencompany_core.workforce import default_workforce
from opencompany_core.worker_queue import QueueError
from opencompany_app.api_schemas import WorkItemCreateInput, WorkItemReassignInput
from opencompany_app.api_dependencies import get_runtime, get_store, require_owner_key, work_item_audit_record
from opencompany_app.runtime import OpenCompanyRuntime


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



@router.post("/work-items/{work_item_id}/reassign", dependencies=[Depends(require_owner_key)])
def reassign_work_item(
    work_item_id: UUID,
    payload: WorkItemReassignInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-authorized reassignment for queued, non-delegated internal work."""
    item = runtime.store.get_work_item(work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    target = runtime.store.get_agent(payload.target_agent_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target agent profile not found.")
    if target.state.value != "active" or target.department != item.department or not target.role_key:
        raise HTTPException(status_code=422, detail="Target must be an active agent in the same department.")
    try:
        department = default_organization().get(item.department)
        role = default_workforce().get(target.role_key)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    expected_team = (
        "executive" if target.role_key == "chief_executive_orchestrator"
        else "management" if target.role_key == department.manager_role_key
        else role.team_key
    )
    if target.role_key not in department.role_keys or target.team_key != expected_team:
        raise HTTPException(status_code=422, detail="Target agent role/team is not authorized for this department.")
    from datetime import datetime, timezone
    from uuid import uuid4
    record = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action="work_item.reassigned",
        subject_type="work_item", subject_id=str(work_item_id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={
            "previous_agent_id": str(item.assigned_agent_id) if item.assigned_agent_id else None,
            "target_agent_id": str(target.id), "role_key": target.role_key,
            "team_key": target.team_key, "business_id": item.business_id,
            "rationale": payload.rationale,
        },
    )
    try:
        return runtime.queue.reassign_queued_work_item(
            work_item_id, target.id, record,
            expected_current_agent_id=item.assigned_agent_id,
        )
    except QueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
