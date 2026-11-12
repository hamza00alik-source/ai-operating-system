"""Owner-authenticated work-item lifecycle, review and deliverable routes."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import AgentState, AuditRecord, TaskState
from opencompany_core.lifecycle import StateTransitionError, transition_work_item
from opencompany_core.persistence import SQLiteStore
from opencompany_core.worker_queue import QueueError
from opencompany_core.learning import OutcomeEvaluation, OutcomeGrade
from opencompany_app.api_schemas import WorkItemReviewInput, WorkItemTransitionInput
from opencompany_app.api_dependencies import (
    _auto_queue_approved_work_enabled,
    _auto_queue_task,
    _free_provider_ready,
    get_delegation_store,
    get_runtime,
    get_store,
    require_owner_key,
    work_item_audit_record as _record,
)
from opencompany_app.routers.handoffs import _handoff_payload
from opencompany_app.runtime import OpenCompanyRuntime
from opencompany_core.delegation_records import DelegationRepository


router = APIRouter()


@router.get("/work-items/{item_id}/workflow", dependencies=[Depends(require_owner_key)])
def get_work_item_workflow(
    item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
    delegations: DelegationRepository = Depends(get_delegation_store),
) -> dict:
    """Return the complete owner-facing lifecycle and business-scoped delegation view."""
    parent = store.get_work_item(item_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Work item not found.")

    profiles = {str(agent.id): agent for agent in store.list_agents(limit=1000)}
    manager = profiles.get(str(parent.assigned_agent_id)) if parent.assigned_agent_id else None
    proposals = delegations.list_for_parent(item_id)
    children_by_id = {}
    for proposal in proposals:
        for child in proposal["children"]:
            child_id = str(child["id"])
            task = store.get_work_item(UUID(child_id))
            if task is None:
                children_by_id[child_id] = {
                    "id": child_id, "title": child["title"], "role_key": child["role_key"],
                    "team_key": child["team_key"], "state": "draft",
                    "assigned_agent_id": child["assigned_agent_id"], "materialized": False,
                    "deliverables": [],
                }
                continue
            if task.business_id != parent.business_id:
                raise HTTPException(status_code=409, detail="Delegated work crossed a business boundary.")
            agent = profiles.get(str(task.assigned_agent_id)) if task.assigned_agent_id else None
            children_by_id[child_id] = {
                "id": child_id, "title": task.title, "role_key": child["role_key"],
                "team_key": child["team_key"], "state": task.state.value,
                "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
                "assignee_state": agent.state.value if agent else "missing",
                "materialized": True,
                "deliverables": store.list_deliverables(task.id),
            }

    dependency_status = []
    prerequisites = []
    for dependency_id in parent.depends_on:
        dependency = store.get_work_item(dependency_id)
        if dependency is None:
            dependency_status.append({
                "work_item_id": str(dependency_id), "state": "missing",
                "deliverable_count": 0, "completed_with_deliverable": False,
            })
            prerequisites.append({
                "id": str(dependency_id), "state": "missing",
                "title": "Missing prerequisite",
            })
            continue
        if dependency.business_id != parent.business_id:
            raise HTTPException(status_code=409, detail="Work dependency crossed a business boundary.")
        dependency_deliverables = store.list_deliverables(dependency_id)
        dependency_status.append({
            "work_item_id": str(dependency_id), "state": dependency.state.value,
            "deliverable_count": len(dependency_deliverables),
            "completed_with_deliverable": (
                dependency.state == TaskState.COMPLETED and bool(dependency_deliverables)
            ),
        })
        prerequisites.append({
            "id": str(dependency_id), "state": dependency.state.value,
            "title": dependency.title,
        })

    # Keep the lifecycle read model within the same business boundary.
    business_items = [
        candidate for candidate in store.list_work_items(limit=1000)
        if candidate.business_id == parent.business_id
    ]
    dependents = [
        {
            "id": str(candidate.id), "title": candidate.title,
            "department": candidate.department, "state": candidate.state.value,
        }
        for candidate in business_items if item_id in candidate.depends_on
    ]
    synthesis_ready = (
        bool(parent.depends_on)
        and manager is not None
        and manager.state == AgentState.ACTIVE
        and manager.department == parent.department
        and manager.team_key == "management"
        and all(value["completed_with_deliverable"] for value in dependency_status)
    )
    deliverables = store.list_deliverables(item_id)
    handoffs = runtime.handoffs.list_for_work_item(item_id)
    next_action = {
        "draft": "owner_review_and_mark_ready",
        "ready": "owner_confirm_assignment_and_enqueue",
        "blocked": "complete_prerequisites",
        "queued": "worker_execution",
        "in_progress": "wait_for_worker_or_recover_expired_lease",
        "review": "owner_review_deliverables",
        "failed": "owner_retry_or_cancel",
        "completed": "terminal",
        "cancelled": "terminal",
    }.get(parent.state.value, "inspect")

    return {
        "work_item": {
            "id": str(parent.id), "title": parent.title, "objective": parent.objective,
            "department": parent.department, "business_id": parent.business_id,
            "state": parent.state.value,
            "assigned_agent_id": str(parent.assigned_agent_id) if parent.assigned_agent_id else None,
            "depends_on": [str(value) for value in parent.depends_on],
            "created_at": parent.created_at.isoformat(),
            "deliverables": deliverables,
        },
        "next_action": next_action,
        "prerequisites": prerequisites,
        "dependents": dependents,
        "queue": runtime.queue.get_entry(item_id),
        "execution_attempts": list(runtime.queue.list_attempts(item_id)),
        "manager": ({
            "agent_id": str(manager.id), "role_key": manager.role_key,
            "team_key": manager.team_key, "department": manager.department,
            "state": manager.state.value,
        } if manager else None),
        "delegation_proposals": proposals,
        "child_work_items": list(children_by_id.values()),
        "dependencies": dependency_status,
        "manager_synthesis": {
            "ready": synthesis_ready,
            "blocked_by": [
                value["work_item_id"] for value in dependency_status
                if not value["completed_with_deliverable"]
            ],
            "requires_completed_child_deliverables": True,
            "queue_admission_requires_owner_action": True,
        },
        "handoffs": [_handoff_payload(value) for value in handoffs],
        "deliverables": [
            {
                "id": row["id"], "role_key": row["role_key"],
                "provider": row["provider"], "model": row["model"],
                "cost_usd": row["cost_usd"], "review_required": bool(row["review_required"]),
                "created_at": row["created_at"],
            }
            for row in deliverables
        ],
        "counts": {
            "prerequisites": len(prerequisites),
            "completed_prerequisites": sum(1 for value in prerequisites if value["state"] == "completed"),
            "dependents": len(dependents),
            "deliverables": len(deliverables),
            "handoffs": len(handoffs),
            "delegation_proposals": len(proposals),
        },
        "owner_review_required": parent.state == TaskState.REVIEW,
        "external_actions_performed": False,
    }




@router.post("/work-items/{item_id}/review", dependencies=[Depends(require_owner_key)])
def review_work_item(
    item_id: UUID, payload: WorkItemReviewInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    from datetime import datetime, timezone

    reviewed_item = store.get_work_item(item_id)
    if reviewed_item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    action = "work_item.review_approved" if payload.approved else "work_item.review_rejected"
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action=action, subject_type="work_item",
        subject_id=str(item_id), outcome="recorded", correlation_id=str(uuid4()),
        details={"approved": payload.approved, "rationale": payload.rationale,
                 "business_id": reviewed_item.business_id},
    )
    try:
        state = store.review_work_item_with_audit(
            item_id, approved=payload.approved, rationale=payload.rationale, record=event,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if state is None:
        raise HTTPException(status_code=409, detail="Work item is not awaiting review.")
    evaluation_id = None
    evaluation_error = None
    try:
        deliverables = store.list_deliverables(item_id)
        evaluation = OutcomeEvaluation(
            id=uuid4(), work_item_id=item_id, evaluator="owner",
            grade=OutcomeGrade.SUCCESS if payload.approved else OutcomeGrade.PARTIAL,
            rubric_scores={
                "owner_acceptance": 5 if payload.approved else 2,
                "scope_fit": 5 if payload.approved else 2,
                "evidence_quality": 4 if payload.approved else 2,
            },
            evidence_refs=tuple(f"deliverable:{item['id']}" for item in deliverables),
            observations=payload.rationale,
        )
        learning_event = AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
            actor_id="owner", action="learning.review_outcome_recorded",
            subject_type="work_item", subject_id=str(item_id),
            outcome=evaluation.grade.value, correlation_id=str(uuid4()),
            details={"evaluation_id": str(evaluation.id),
                     "business_id": reviewed_item.business_id},
        )
        runtime.learning.save_evaluation(evaluation, learning_event)
        evaluation_id = str(evaluation.id)
    except Exception as exc:
        evaluation_error = type(exc).__name__
    auto_queue = {
        "enabled": _auto_queue_approved_work_enabled(),
        "provider_ready": False,
        "queued_work_item_ids": [],
        "errors": [],
    }
    if payload.approved and auto_queue["enabled"]:
        try:
            auto_queue["provider_ready"] = _free_provider_ready(runtime)
            if auto_queue["provider_ready"]:
                completed_ids = {item.id for item in store.list_work_items(limit=1000)
                                 if item.state == TaskState.COMPLETED}
                for candidate in store.list_work_items(limit=1000):
                    if (
                        candidate.state != TaskState.READY
                        or item_id not in candidate.depends_on
                        or candidate.assigned_agent_id is None
                        or not set(candidate.depends_on).issubset(completed_ids)
                    ):
                        continue
                    approved_proposals = runtime.delegations.list_for_parent(candidate.id)
                    if not any(value["status"] == "approved" for value in approved_proposals):
                        continue
                    agent = store.get_agent(candidate.assigned_agent_id)
                    if agent is None or agent.state != AgentState.ACTIVE:
                        auto_queue["errors"].append({
                            "work_item_id": str(candidate.id), "error_type": "InactiveManager",
                        })
                        continue
                    try:
                        _auto_queue_task(
                            runtime, candidate, agent,
                            action="work_item.manager_synthesis_auto_queued",
                        )
                        auto_queue["queued_work_item_ids"].append(str(candidate.id))
                    except (QueueError, ValueError) as exc:
                        auto_queue["errors"].append({
                            "work_item_id": str(candidate.id), "error_type": type(exc).__name__,
                        })
        except Exception as exc:
            auto_queue["errors"].append({"error_type": type(exc).__name__})
    return {
        "item_id": str(item_id), "state": state.value, "approved": payload.approved,
        "evaluation_id": evaluation_id, "evaluation_recorded": evaluation_id is not None,
        "evaluation_error": evaluation_error,
        "auto_queue": auto_queue,
    }



@router.post("/work-items/{item_id}/transition", dependencies=[Depends(require_owner_key)])
def change_work_item_state(
    item_id: UUID,
    payload: WorkItemTransitionInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    if item.state == TaskState.REVIEW and payload.target_state == TaskState.COMPLETED:
        raise HTTPException(status_code=409, detail="Use the owner review endpoint to approve a review-required deliverable.")
    if item.state in {TaskState.QUEUED, TaskState.IN_PROGRESS} and payload.target_state == TaskState.CANCELLED:
        raise HTTPException(
            status_code=409,
            detail="Queued or running work cannot be cancelled through a state-only transition. A queue-aware cancellation must first stop or revoke the active lease.",
        )
    if payload.target_state in {TaskState.QUEUED, TaskState.IN_PROGRESS}:
        raise HTTPException(status_code=409, detail="Use owner queue admission and the worker claim pipeline for execution states.")
    known = {value.id: value for value in store.list_work_items(limit=1000)}
    try:
        changed = transition_work_item(item, payload.target_state, known_items=known)
    except StateTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_work_item_with_audit(changed, _record(changed, "work_item.state_changed"))
    return {"item_id": str(changed.id), "state": changed.state.value}




@router.get("/work-items/{item_id}/deliverables", dependencies=[Depends(require_owner_key)])
def list_work_item_deliverables(
    item_id: UUID, store: SQLiteStore = Depends(get_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    artifacts = store.list_deliverables(item_id)
    return {"count": len(artifacts), "deliverables": artifacts}


