"""Owner-authenticated agent handoff lifecycle routes."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.collaboration import AgentHandoff, HandoffState, accept_handoff, decline_handoff, deliver_handoff
from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_app.api_schemas import HandoffCreateInput, HandoffDeliverInput
from opencompany_app.api_dependencies import get_runtime, get_store, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


def _handoff_payload(item: AgentHandoff) -> dict:
    return {
        "id": str(item.id), "work_item_id": str(item.work_item_id),
        "sender_agent_id": str(item.sender_agent_id),
        "recipient_agent_id": str(item.recipient_agent_id),
        "purpose": item.purpose, "requested_result": item.requested_result,
        "context": item.context, "artifact_ids": [str(value) for value in item.artifact_ids],
        "state": item.state.value, "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "response_artifact_ids": [str(value) for value in item.response_artifact_ids],
    }



@router.post("/work-items/{item_id}/handoffs", dependencies=[Depends(require_owner_key)])
def create_agent_handoff(
    item_id: UUID,
    payload: HandoffCreateInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    if item.assigned_agent_id is None:
        raise HTTPException(status_code=409, detail="Only the assigned agent can initiate a handoff.")
    now = datetime.now(timezone.utc)
    handoff = AgentHandoff(
        id=uuid4(), work_item_id=item.id, sender_agent_id=item.assigned_agent_id,
        recipient_agent_id=payload.recipient_agent_id, purpose=payload.purpose,
        requested_result=payload.requested_result, context=payload.context,
        artifact_ids=tuple(payload.artifact_ids), created_at=now, updated_at=now,
    )
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner",
        actor_id="owner", action="owner.proposed_agent_handoff",
        subject_type="agent_handoff", subject_id=str(handoff.id), outcome="proposed",
        correlation_id=str(uuid4()),
        details={"work_item_id": str(item.id), "business_id": item.business_id,
                 "recipient_agent_id": str(payload.recipient_agent_id)},
    )
    try:
        runtime.handoffs.create(handoff, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"handoff": _handoff_payload(handoff), "execution_started": False}


@router.get("/work-items/{item_id}/handoffs", dependencies=[Depends(require_owner_key)])
def list_agent_handoffs(
    item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    handoffs = runtime.handoffs.list_for_work_item(item_id)
    return {"count": len(handoffs), "handoffs": [_handoff_payload(item) for item in handoffs]}


@router.post("/handoffs/{handoff_id}/accept", dependencies=[Depends(require_owner_key)])
def accept_agent_handoff(
    handoff_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    handoff = runtime.handoffs.get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found.")
    work_item = store.get_work_item(handoff.work_item_id)
    if work_item is None:
        raise HTTPException(status_code=404, detail="Handoff work item not found.")
    now = datetime.now(timezone.utc)
    try:
        updated = accept_handoff(handoff, at=now)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="owner.accepted_agent_handoff", subject_type="agent_handoff",
        subject_id=str(handoff.id), outcome="accepted", correlation_id=str(uuid4()),
        details={"recipient_agent_id": str(handoff.recipient_agent_id),
                 "work_item_id": str(work_item.id), "business_id": work_item.business_id},
    )
    if not runtime.handoffs.transition(updated, HandoffState.PROPOSED, event):
        raise HTTPException(status_code=409, detail="Handoff changed; reload before retrying.")
    return {"handoff": _handoff_payload(updated), "execution_started": False}


@router.post("/handoffs/{handoff_id}/decline", dependencies=[Depends(require_owner_key)])
def decline_agent_handoff(
    handoff_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    handoff = runtime.handoffs.get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found.")
    work_item = store.get_work_item(handoff.work_item_id)
    if work_item is None:
        raise HTTPException(status_code=404, detail="Handoff work item not found.")
    now = datetime.now(timezone.utc)
    try:
        updated = decline_handoff(handoff, at=now)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="owner.declined_agent_handoff", subject_type="agent_handoff",
        subject_id=str(handoff.id), outcome="declined", correlation_id=str(uuid4()),
        details={"recipient_agent_id": str(handoff.recipient_agent_id),
                 "work_item_id": str(work_item.id), "business_id": work_item.business_id},
    )
    if not runtime.handoffs.transition(updated, HandoffState.PROPOSED, event):
        raise HTTPException(status_code=409, detail="Handoff changed; reload before retrying.")
    return {"handoff": _handoff_payload(updated)}


@router.post("/handoffs/{handoff_id}/deliver", dependencies=[Depends(require_owner_key)])
def deliver_agent_handoff(
    handoff_id: UUID,
    payload: HandoffDeliverInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    handoff = runtime.handoffs.get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found.")
    work_item = store.get_work_item(handoff.work_item_id)
    if work_item is None:
        raise HTTPException(status_code=404, detail="Handoff work item not found.")
    now = datetime.now(timezone.utc)
    try:
        updated = deliver_handoff(handoff, response_artifact_ids=payload.response_artifact_ids, at=now)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="owner.recorded_handoff_delivery", subject_type="agent_handoff",
        subject_id=str(handoff.id), outcome="delivered", correlation_id=str(uuid4()),
        details={"response_artifact_ids": [str(value) for value in payload.response_artifact_ids],
                 "work_item_id": str(work_item.id), "business_id": work_item.business_id},
    )
    if not runtime.handoffs.transition(updated, HandoffState.ACCEPTED, event):
        raise HTTPException(status_code=409, detail="Handoff changed; reload before retrying.")
    return {"handoff": _handoff_payload(updated)}

