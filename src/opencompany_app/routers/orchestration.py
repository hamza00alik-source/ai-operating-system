"""Owner-approved executive planning and department delegation routes."""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import BUSINESS_UNIT_IDS, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore
from opencompany_core.organization import default_organization
from opencompany_core.manager_orchestration import plan_department_work
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.worker_queue import QueueError
from opencompany_core.manager_ai import ManagerPlanningError, recommend_department_plan
from opencompany_core.executive_ai import ExecutivePlanningError, create_executive_plan
from opencompany_core.model_gateway import CostPolicyViolation, NoEligibleProvider, ProviderUnavailable
from opencompany_app.api_schemas import DelegationPreviewInput, ExecutivePlanInput, ManagerProposalInput
from opencompany_app.api_dependencies import (
    _auto_queue_approved_work_enabled, _auto_queue_task, _free_provider_ready,
    get_delegation_store, get_runtime, get_store, require_owner_key,
)
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


@router.post("/executive/plan", dependencies=[Depends(require_owner_key)])
def create_executive_work_plan(
    payload: ExecutivePlanInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    """Ask the active CEO orchestrator to decompose an owner objective into draft tasks."""
    if payload.business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    ceo = next(
        (agent for agent in store.list_agents(limit=1000)
         if agent.role_key == "chief_executive_orchestrator"),
        None,
    )
    if ceo is None or ceo.state != AgentState.ACTIVE:
        raise HTTPException(status_code=409, detail="The Chief Executive Orchestrator must be provisioned and explicitly ACTIVE.")
    try:
        plan = create_executive_plan(
            payload.title, payload.objective, runtime.gateway,
            max_tasks=payload.max_tasks, business_id=payload.business_id,
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=503, detail="No owner-configured free model provider is available for CEO planning.") from exc
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        # Adapter diagnostics are sanitized and bounded; never expose credentials
        # or raw upstream response bodies in the owner-facing API.
        reason = " ".join(str(exc).split())[:600] or type(exc).__name__
        raise HTTPException(
            status_code=502,
            detail=f"CEO model request failed safely: {type(exc).__name__}: {reason}",
        ) from exc
    except ExecutivePlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    correlation_id = str(uuid4())
    now = datetime.now(timezone.utc)
    records = tuple(
        AuditRecord(
            id=uuid4(), occurred_at=now, actor_type="agent", actor_id=str(ceo.id),
            action="executive.draft_work_item_created", subject_type="work_item",
            subject_id=str(item.id), outcome="drafted", correlation_id=correlation_id,
            details={"provider": plan.provider, "model": plan.model,
                     "plan_title": payload.title, "business_id": item.business_id},
        )
        for item in plan.work_items
    )
    try:
        store.save_work_items_with_audit(plan.work_items, records)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Could not persist the complete executive plan: {type(exc).__name__}") from exc
    return {
        "plan_title": payload.title,
        "business_id": payload.business_id,
        "rationale": plan.rationale,
        "provider": plan.provider,
        "model": plan.model,
        "created_count": len(plan.work_items),
        "items": [
            {
                "id": str(item.id), "title": item.title, "objective": item.objective,
                "department": item.department, "business_id": item.business_id,
                "state": item.state.value,
                "depends_on": [str(value) for value in item.depends_on],
            }
            for item in plan.work_items
        ],
        "owner_review_required": True,
        "queue_entries_created": False,
        "execution_started": False,
    }


@router.post("/work-items/{item_id}/manager-proposal", dependencies=[Depends(require_owner_key)])
def create_ai_manager_proposal(
    item_id: UUID,
    payload: ManagerProposalInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
    delegations: DelegationRepository = Depends(get_delegation_store),
) -> dict:
    """Ask the active department manager to propose a team; owner approval remains mandatory."""
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    if item.state != TaskState.DRAFT or item.assigned_agent_id is not None:
        raise HTTPException(status_code=409, detail="Manager planning is allowed only for unassigned draft work items.")
    manager_role = default_organization().get(item.department).manager_role_key
    manager = next(
        (agent for agent in store.list_agents(limit=1000)
         if agent.role_key == manager_role and agent.department == item.department),
        None,
    )
    if (
        manager is None or manager.state != AgentState.ACTIVE
        or manager.role_key != manager_role or manager.team_key != "management"
        or manager.department != item.department
    ):
        raise HTTPException(
            status_code=409,
            detail="The department manager must be explicitly ACTIVE with the expected role, department, and management team.",
        )
    try:
        recommendation = recommend_department_plan(
            item, runtime.gateway, max_specialists=payload.max_specialists
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=503, detail="No owner-configured free model provider is available for manager planning.") from exc
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        raise HTTPException(status_code=502, detail=f"Manager model request failed safely: {type(exc).__name__}") from exc
    except ManagerPlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    plan = recommendation.plan
    profiles = store.list_agents(limit=1000)
    children = []
    if plan.mode.value == "manager_direct":
        children.append({
            "assigned_agent_id": str(manager.id), "role_key": plan.manager_role_key,
            "team_key": "management", "title": f"{plan.manager_title}: {item.title}",
            "objective": f"Handle parent work item {item.id}. Objective: {item.objective} Produce an internal draft for owner review.",
        })
    elif plan.mode.value == "specialist_team":
        for specialist in plan.specialists:
            profile = next(
                (agent for agent in profiles
                 if agent.role_key == specialist.role_key and agent.team_key == specialist.team_key
                 and agent.department == item.department),
                None,
            )
            if (
                profile is None
                or profile.role_key != specialist.role_key
                or profile.team_key != specialist.team_key
                or profile.department != item.department
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"Specialist must be provisioned, ACTIVE, and correctly assigned: {specialist.role_key}",
                )
            children.append({
                "assigned_agent_id": str(profile.id), "role_key": specialist.role_key,
                "team_key": specialist.team_key, "title": f"{specialist.title}: {item.title}",
                "objective": (
                    f"Support parent work item {item.id}. Parent objective: {item.objective} "
                    f"Manager rationale: {recommendation.rationale} "
                    f"Required capabilities: {', '.join(recommendation.required_capabilities)}. "
                    "Produce an internal draft for manager review only."
                ),
            })
    proposal = delegations.create_proposal(
        parent_work_item_id=item.id,
        request={
            "required_capabilities": list(recommendation.required_capabilities),
            "max_specialists": payload.max_specialists,
            "manager_rationale": recommendation.rationale,
            "planner_provider": recommendation.provider,
            "planner_model": recommendation.model,
            "selected_team_keys": list(dict.fromkeys(specialist.team_key for specialist in plan.specialists)),
        },
        manager_agent_id=manager.id,
        mode=plan.mode.value,
        team_key=plan.selected_team_key,
        children=children,
    )
    return {
        "proposal": proposal,
        "manager": {"agent_id": str(manager.id), "role_key": manager_role, "state": manager.state.value},
        "manager_ai": {
            "provider": recommendation.provider, "model": recommendation.model,
            "rationale": recommendation.rationale,
        },
        "required_capabilities": list(recommendation.required_capabilities),
        "mode": plan.mode.value,
        "selected_team_key": plan.selected_team_key,
        "uncovered_capabilities": list(plan.uncovered_capabilities),
        "owner_approval_required": True,
        "assignment_performed": False,
        "queue_entries_created": False,
        "execution_started": False,
    }


@router.post("/work-items/{item_id}/delegation-proposals", dependencies=[Depends(require_owner_key)])
def create_work_item_delegation_proposal(
    item_id: UUID,
    payload: DelegationPreviewInput,
    store: SQLiteStore = Depends(get_store),
    delegations: DelegationRepository = Depends(get_delegation_store),
) -> dict:
    """Persist a manager's proposed team and draft child tasks; never enqueue them."""
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    if item.state != TaskState.DRAFT or item.assigned_agent_id is not None:
        raise HTTPException(status_code=409, detail="Delegation planning is allowed only for unassigned draft work items.")
    try:
        plan = plan_department_work(item, payload.required_capabilities, max_specialists=payload.max_specialists)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profiles = store.list_agents(limit=1000)
    manager = next((agent for agent in profiles if agent.role_key == plan.manager_role_key and agent.department == item.department), None)
    if (
        manager is None or manager.state in {AgentState.PAUSED, AgentState.RETIRED}
        or manager.role_key != plan.manager_role_key
        or manager.team_key != "management"
        or manager.department != item.department
    ):
        raise HTTPException(
            status_code=409,
            detail="The department manager must be ACTIVE with the expected role, department, and management team.",
        )
    children = []
    if plan.mode.value == "manager_direct":
        children.append({
            "assigned_agent_id": str(manager.id), "role_key": plan.manager_role_key,
            "team_key": "management", "title": f"{plan.manager_title}: {item.title}",
            "objective": f"Handle parent work item {item.id}. Objective: {item.objective} Produce an internal draft for owner review.",
        })
    elif plan.mode.value == "specialist_team":
        for specialist in plan.specialists:
            profile = next((agent for agent in profiles if agent.role_key == specialist.role_key and agent.team_key == specialist.team_key and agent.department == item.department), None)
            if (
                profile is None
                or profile.role_key != specialist.role_key
                or profile.team_key != specialist.team_key
                or profile.department != item.department
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"Specialist must be provisioned, ACTIVE, and correctly assigned: {specialist.role_key}",
                )
            children.append({
                "assigned_agent_id": str(profile.id), "role_key": specialist.role_key,
                "team_key": specialist.team_key, "title": f"{specialist.title}: {item.title}",
                "objective": f"Support parent work item {item.id}. Parent objective: {item.objective} Required capabilities: {', '.join(payload.required_capabilities)}. Produce an internal draft for manager review only.",
            })
    return delegations.create_proposal(
        parent_work_item_id=item.id,
        request={
            "required_capabilities": payload.required_capabilities,
            "max_specialists": payload.max_specialists,
            "selected_team_keys": list(dict.fromkeys(specialist.team_key for specialist in plan.specialists)),
        },
        manager_agent_id=manager.id,
        mode=plan.mode.value,
        team_key=plan.selected_team_key,
        children=children,
    )


@router.post("/work-items/{item_id}/delegation-proposals/{proposal_id}/approve", dependencies=[Depends(require_owner_key)])
def approve_work_item_delegation_proposal(
    item_id: UUID, proposal_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
    delegations: DelegationRepository = Depends(get_delegation_store),
) -> dict:
    """Owner approval materializes child tasks as READY; it never queues them."""
    from datetime import datetime, timezone

    parent = store.get_work_item(item_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent work item not found.")
    if parent.state != TaskState.DRAFT or parent.assigned_agent_id is not None:
        raise HTTPException(status_code=409, detail="The parent work item changed after planning; create a fresh draft proposal.")
    proposal = delegations.get_proposal(proposal_id)
    if proposal is None or proposal["parent_work_item_id"] != str(item_id):
        raise HTTPException(status_code=404, detail="Delegation proposal not found for this parent.")
    if proposal["status"] != "draft":
        raise HTTPException(status_code=409, detail="Delegation proposal is no longer awaiting approval.")
    if proposal["mode"] == "owner_review" or not proposal["children"]:
        raise HTTPException(status_code=409, detail="Unresolved capabilities prevent approval.")
    profiles = {str(agent.id): agent for agent in store.list_agents(limit=1000)}
    tasks, events = [], []
    for child in proposal["children"]:
        agent = profiles.get(child["assigned_agent_id"])
        if agent is None or agent.state != AgentState.ACTIVE:
            raise HTTPException(status_code=409, detail=f"Assigned profile must exist and be explicitly active: {child['role_key']}")
        if (agent.role_key != child["role_key"] or agent.team_key != child["team_key"]
                or agent.department != parent.department):
            raise HTTPException(status_code=409, detail=f"Assigned profile identity changed: {child['role_key']}")
        task = WorkItem(
            id=UUID(child["id"]), title=child["title"], objective=child["objective"],
            department=parent.department, state=TaskState.READY, assigned_agent_id=agent.id,
            business_id=parent.business_id,
        )
        tasks.append(task)
        events.append(AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="delegation.child_task_materialized",
            subject_type="work_item", subject_id=str(task.id), outcome="recorded",
            correlation_id=str(proposal_id),
            details={"parent_work_item_id": str(item_id), "agent_id": str(agent.id),
                     "role_key": agent.role_key, "team_key": agent.team_key,
                     "state": TaskState.READY.value},
        ))
    events.append(AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action="delegation.proposal_approved",
        subject_type="delegation_proposal", subject_id=str(proposal_id),
        outcome="recorded", correlation_id=str(proposal_id),
        details={"parent_work_item_id": str(item_id), "child_count": len(tasks),
                 "queue_entries_created": False},
    ))
    manager = profiles.get(proposal["manager_agent_id"])
    expected_manager_role = default_organization().get(parent.department).manager_role_key
    if (
        manager is None or manager.state != AgentState.ACTIVE
        or manager.role_key != expected_manager_role
        or manager.department != parent.department
        or manager.team_key != "management"
    ):
        raise HTTPException(status_code=409, detail="The assigned department manager must remain ACTIVE with the expected role before approval.")
    parent_update = replace(
        parent,
        state=TaskState.READY,
        assigned_agent_id=manager.id,
        depends_on=tuple(task.id for task in tasks),
    )
    events.append(AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action="delegation.manager_synthesis_assigned",
        subject_type="work_item", subject_id=str(parent.id), outcome="recorded",
        correlation_id=str(proposal_id),
        details={
            "manager_agent_id": str(manager.id),
            "manager_role_key": manager.role_key,
            "dependency_work_item_ids": [str(task.id) for task in tasks],
            "state": TaskState.READY.value,
        },
    ))
    try:
        saved = store.approve_delegation_proposal(
            proposal_id, tuple(tasks), tuple(events), parent_update=parent_update,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not saved:
        raise HTTPException(status_code=409, detail="Proposal was approved or changed concurrently.")
    auto_queue = {
        "enabled": _auto_queue_approved_work_enabled(),
        "provider_ready": False,
        "queued_work_item_ids": [],
        "errors": [],
    }
    if auto_queue["enabled"]:
        try:
            auto_queue["provider_ready"] = _free_provider_ready(runtime)
            if auto_queue["provider_ready"]:
                for task in tasks:
                    agent = profiles[str(task.assigned_agent_id)]
                    try:
                        _auto_queue_task(
                            runtime, task, agent,
                            action="work_item.auto_queued_after_delegation_approval",
                        )
                        auto_queue["queued_work_item_ids"].append(str(task.id))
                    except (QueueError, ValueError) as exc:
                        auto_queue["errors"].append({
                            "work_item_id": str(task.id), "error_type": type(exc).__name__,
                        })
        except Exception as exc:
            auto_queue["errors"].append({"error_type": type(exc).__name__})
    return {
        "proposal_id": str(proposal_id), "status": "approved",
        "auto_queue": auto_queue,
        "materialized_work_items": [
            {"id": str(task.id), "assigned_agent_id": str(task.assigned_agent_id),
             "state": "queued" if str(task.id) in auto_queue["queued_work_item_ids"] else task.state.value}
            for task in tasks
        ],
        "manager_synthesis_work_item": {
            "id": str(parent_update.id),
            "assigned_agent_id": str(manager.id),
            "role_key": manager.role_key,
            "state": parent_update.state.value,
            "depends_on": [str(value) for value in parent_update.depends_on],
            "ready_after_all_children_are_owner_approved": True,
        },
        "queue_entries_created": bool(auto_queue["queued_work_item_ids"]),
        "execution_started": False,
    }


@router.get("/work-items/{item_id}/delegation-proposals", dependencies=[Depends(require_owner_key)])
def list_work_item_delegation_proposals(
    item_id: UUID,
    store: SQLiteStore = Depends(get_store),
    delegations: DelegationRepository = Depends(get_delegation_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    proposals = delegations.list_for_parent(item_id)
    return {"count": len(proposals), "proposals": proposals}



