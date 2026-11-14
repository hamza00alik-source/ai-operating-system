"""Owner-authenticated agent profile and workforce bootstrap routes."""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import AgentState, AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_core.provisioning import (
    bootstrap_department_managers,
    bootstrap_executive_orchestrator,
    bootstrap_specialist_profiles,
)
from opencompany_app.api_schemas import AgentStateChangeInput
from opencompany_app.api_dependencies import get_store, require_owner_key


router = APIRouter()


@router.get("/agents", dependencies=[Depends(require_owner_key)])
def list_agents(store: SQLiteStore = Depends(get_store)) -> dict:
    agents = store.list_agents(limit=1000)
    return {
        "count": len(agents),
        "agents": [
            {
                "id": str(item.id), "name": item.name,
                "department": item.department, "purpose": item.purpose,
                "capabilities": list(item.capabilities), "role_key": item.role_key,
                "team_key": item.team_key,
                "state": item.state.value, "revision": item.revision,
            }
            for item in agents
        ],
    }


@router.post("/agents/{agent_id}/state", dependencies=[Depends(require_owner_key)])
def change_agent_state(
    agent_id: UUID,
    payload: AgentStateChangeInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    agent = store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    if agent.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="Agent profile revision is stale.")
    if agent.state == payload.target_state:
        return {
            "agent_id": str(agent.id), "state": agent.state.value,
            "revision": agent.revision, "worker_started": False,
            "unchanged": True,
        }
    allowed = {
        AgentState.DRAFT: {AgentState.ACTIVE, AgentState.RETIRED},
        AgentState.ACTIVE: {AgentState.PAUSED, AgentState.RETIRED},
        AgentState.PAUSED: {AgentState.ACTIVE, AgentState.RETIRED},
        AgentState.RETIRED: set(),
    }
    if payload.target_state not in allowed[agent.state]:
        raise HTTPException(status_code=409, detail="Requested agent state transition is not allowed.")
    if payload.target_state == AgentState.ACTIVE and not (agent.role_key and agent.team_key):
        raise HTTPException(status_code=409, detail="Agent must have a verified role and team before activation.")
    changed = replace(agent, state=payload.target_state, revision=agent.revision + 1)
    from datetime import datetime, timezone
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action="agent.state_changed",
        subject_type="agent_profile", subject_id=str(agent.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={
            "from": agent.state.value, "to": changed.state.value,
            "role_key": agent.role_key, "team_key": agent.team_key,
            "revision": changed.revision,
        },
    )
    if not store.update_agent_with_audit(
        changed, event, expected_revision=payload.expected_revision
    ):
        raise HTTPException(status_code=409, detail="Agent profile changed concurrently; reload and retry.")
    return {
        "agent_id": str(changed.id), "state": changed.state.value,
        "revision": changed.revision, "worker_started": False,
    }


@router.post("/agents/bootstrap", dependencies=[Depends(require_owner_key)])
def bootstrap_agents(store: SQLiteStore = Depends(get_store)) -> dict:
    agents = bootstrap_department_managers(store)
    return {
        "count": len(agents),
        "created_profiles": len(agents),
        "all_draft": all(item.state.value == "draft" for item in agents),
        "agents": [
            {"id": str(item.id), "department": item.department,
             "role_capabilities": list(item.capabilities), "state": item.state.value}
            for item in agents
        ],
        "execution_started": False,
    }


@router.post("/agents/bootstrap-executive", dependencies=[Depends(require_owner_key)])
def bootstrap_executive(store: SQLiteStore = Depends(get_store)) -> dict:
    agent = bootstrap_executive_orchestrator(store)
    return {
        "count": 1,
        "agent": {"id": str(agent.id), "name": agent.name,
                  "department": agent.department, "state": agent.state.value},
        "execution_started": False,
    }


@router.post("/agents/bootstrap-specialists", dependencies=[Depends(require_owner_key)])
def bootstrap_specialists(store: SQLiteStore = Depends(get_store)) -> dict:
    agents = bootstrap_specialist_profiles(store)
    return {
        "count": len(agents),
        "created_profiles": len(agents),
        "all_draft": all(item.state.value == "draft" for item in agents),
        "agents": [
            {"id": str(item.id), "name": item.name, "department": item.department,
             "capabilities": list(item.capabilities), "state": item.state.value}
            for item in agents
        ],
        "execution_started": False,
    }

