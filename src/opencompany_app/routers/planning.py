"""Planning previews, guarded queue admission and delegation previews."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import BUSINESS_UNIT_IDS, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore
from opencompany_core.planning import PlanError, WorkPlan, action_requires_owner_approval
from opencompany_core.workforce import default_workforce
from opencompany_core.organization import default_organization
from opencompany_core.worker_queue import QueueError
from opencompany_app.api_schemas import PlanPreviewInput, DelegationPreviewInput
from opencompany_app.api_dependencies import (
    _auto_queue_task, get_runtime, get_store, require_owner_key,
)
from opencompany_app.runtime import OpenCompanyRuntime
from opencompany_core.manager_orchestration import plan_department_work


planning_router = APIRouter()
queue_router = APIRouter()
delegation_router = APIRouter()


@planning_router.post("/plans/preview")
def preview_plan(payload: PlanPreviewInput) -> dict:
    if any(candidate.business_id not in BUSINESS_UNIT_IDS for candidate in payload.items):
        raise HTTPException(status_code=422, detail="Plan contains an unknown business unit.")
    try:
        for candidate in payload.items:
            default_organization().get(candidate.department)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    items = tuple(
        WorkItem(
            id=item.id, title=item.title, objective=item.objective,
            department=item.department, state=item.state, depends_on=item.depends_on,
            business_id=item.business_id,
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


@planning_router.get("/policy/protected-actions")
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


@queue_router.post("/work-items/{item_id}/enqueue", dependencies=[Depends(require_owner_key)])
def enqueue_work_item(
    item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner explicitly admits an approved, assigned READY task to the durable queue."""
    from datetime import datetime, timezone

    item = runtime.store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    if item.state != TaskState.READY:
        raise HTTPException(status_code=409, detail="Only READY tasks can be queued.")
    # Enforce dependency gates at the durable queue boundary, not only at
    # lifecycle transitions. Delegated manager-synthesis tasks are READY while
    # their children are running, so state alone is not sufficient authority.
    for dependency_id in item.depends_on:
        dependency = runtime.store.get_work_item(dependency_id)
        if dependency is None:
            raise HTTPException(status_code=409, detail="A required prerequisite is missing.")
        if dependency.business_id != item.business_id:
            raise HTTPException(status_code=409, detail="A required prerequisite crosses a business boundary.")
        if dependency.state != TaskState.COMPLETED:
            raise HTTPException(status_code=409, detail="All prerequisites must be completed and owner-approved before queue admission.")
        if not runtime.store.list_deliverables(dependency_id):
            raise HTTPException(status_code=409, detail="Every completed prerequisite must have a saved deliverable before queue admission.")
    if item.assigned_agent_id is None:
        raise HTTPException(status_code=409, detail="An explicit assignee is required before queue admission.")
    agent = runtime.store.get_agent(item.assigned_agent_id)
    if agent is None or agent.state != AgentState.ACTIVE or agent.department != item.department:
        raise HTTPException(status_code=409, detail="Assigned agent must be active in the task department.")
    if not agent.role_key or not agent.team_key:
        raise HTTPException(status_code=409, detail="Assigned agent must have a verified role and team.")
    try:
        department = default_organization().get(item.department)
        role = default_workforce().get(agent.role_key)
    except LookupError as exc:
        raise HTTPException(status_code=409, detail="Assigned agent role is not in the original workforce catalogue.") from exc
    expected_team = (
        "executive" if agent.role_key == "chief_executive_orchestrator"
        else "management" if agent.role_key == department.manager_role_key
        else role.team_key
    )
    if agent.role_key not in department.role_keys or expected_team != agent.team_key:
        raise HTTPException(status_code=409, detail="Assigned agent role or team does not match the department catalogue.")
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(status_code=503, detail="No owner-configured free inference provider is available; queue admission is blocked.")
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action="work_item.queued",
        subject_type="work_item", subject_id=str(item.id), outcome="recorded",
        correlation_id=str(uuid4()),
        details={"agent_id": str(agent.id), "role_key": agent.role_key,
                 "team_key": agent.team_key, "business_id": item.business_id},
    )
    try:
        runtime.queue.enqueue_authorized(
            item, agent.id, {"role_key": agent.role_key, "team_key": agent.team_key}, event
        )
    except (QueueError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "item_id": str(item.id), "agent_id": str(agent.id),
        "state": TaskState.QUEUED.value, "queue_admitted": True,
        "worker_started": False,
    }


@delegation_router.post("/work-items/{item_id}/delegation-preview", dependencies=[Depends(require_owner_key)])
def preview_work_item_delegation(
    item_id: UUID,
    payload: DelegationPreviewInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    try:
        plan = plan_department_work(
            item, payload.required_capabilities,
            max_specialists=payload.max_specialists,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "work_item_id": plan.work_item_id,
        "department": plan.department,
        "manager": {
            "role_key": plan.manager_role_key,
            "title": plan.manager_title,
        },
        "mode": plan.mode.value,
        "selected_team_key": plan.selected_team_key,
        "selected_team_keys": list(dict.fromkeys(specialist.team_key for specialist in plan.specialists)),
        "specialists": [
            {
                "role_key": specialist.role_key,
                "title": specialist.title,
                "team_key": specialist.team_key,
                "matched_capabilities": list(specialist.matched_capabilities),
                "supporting_member": specialist.supporting_member,
                "permitted_outputs": list(specialist.permitted_outputs),
            }
            for specialist in plan.specialists
        ],
        "manager_covered_capabilities": list(plan.manager_covered_capabilities),
        "uncovered_capabilities": list(plan.uncovered_capabilities),
        "assignment_performed": plan.assignment_performed,
        "execution_started": plan.execution_started,
    }



@queue_router.post("/workflows/reconcile", dependencies=[Depends(require_owner_key)])
def reconcile_interrupted_workflows(
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-triggered, idempotent recovery of eligible manager synthesis queue admissions.

    This only admits work to the durable queue. It never starts workers or invokes
    a model provider. Existing queue entries are left untouched.
    """
    queued_ids = []
    skipped = []
    errors = []
    ready = [
        item for item in runtime.store.list_work_items(limit=1000)
        if item.state == TaskState.READY and item.depends_on
    ]
    provider_ready = bool(runtime.gateway.eligible_providers(request_budget_usd=0.0))
    for task in ready:
        proposals = runtime.delegations.list_for_parent(task.id)
        approved = [
            proposal for proposal in proposals
            if proposal["status"] == "approved"
            and proposal.get("manager_agent_id")
            and {UUID(child["id"]) for child in proposal["children"]} == set(task.depends_on)
        ]
        if not approved:
            continue
        proposal = approved[-1]
        proposal_manager_id = UUID(proposal["manager_agent_id"])
        if task.assigned_agent_id != proposal_manager_id:
            skipped.append({"work_item_id": str(task.id), "reason": "manager_assignment_changed"})
            continue
        dependencies_ready = True
        for dependency_id in task.depends_on:
            dependency = runtime.store.get_work_item(dependency_id)
            if dependency is None or dependency.business_id != task.business_id:
                skipped.append({"work_item_id": str(task.id), "reason": "missing_or_cross_business_prerequisite"})
                dependencies_ready = False
                break
            if dependency.state != TaskState.COMPLETED or not runtime.store.list_deliverables(dependency_id):
                skipped.append({"work_item_id": str(task.id), "reason": "prerequisites_not_approved_with_deliverables"})
                dependencies_ready = False
                break
        if not dependencies_ready:
            continue
        existing = runtime.queue.get_entry(task.id)
        if existing is not None:
            skipped.append({"work_item_id": str(task.id), "reason": "queue_entry_already_exists"})
            continue
        if not provider_ready:
            skipped.append({"work_item_id": str(task.id), "reason": "no_zero_cost_provider_available"})
            continue
        agent = runtime.store.get_agent(proposal_manager_id)
        if agent is None or agent.state != AgentState.ACTIVE:
            skipped.append({"work_item_id": str(task.id), "reason": "manager_not_active"})
            continue
        try:
            _auto_queue_task(
                runtime, task, agent,
                action="work_item.manager_synthesis_reconciled",
            )
            queued_ids.append(str(task.id))
        except (QueueError, ValueError, LookupError) as exc:
            errors.append({
                "work_item_id": str(task.id),
                "error_type": type(exc).__name__,
            })
    return {
        "scanned_ready_tasks": len(ready),
        "provider_ready": provider_ready,
        "queued_work_item_ids": queued_ids,
        "skipped": skipped,
        "errors": errors,
        "worker_started": False,
        "model_invoked": False,
        "external_actions_performed": False,
    }
