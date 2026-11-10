"""Standalone OpenCompany API, independent of legacy AIOS modules.

The service exposes a public read-only health check. All company records and
write operations require an owner API key. No endpoint invokes a model or
performs an external business action.
"""
from __future__ import annotations

import hmac
import os
from dataclasses import replace
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from opencompany_core.domain import AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.lifecycle import StateTransitionError, transition_work_item
from opencompany_core.persistence import SQLiteStore
from opencompany_core.planning import PlanError, WorkPlan, action_requires_owner_approval
from opencompany_core.workforce import default_workforce
from opencompany_core.organization import default_organization
from opencompany_core.media_studio import video_capabilities
from opencompany_core.provider_catalog import free_provider_candidates
from opencompany_core.provisioning import bootstrap_department_managers, bootstrap_specialist_profiles, bootstrap_executive_orchestrator
from opencompany_app.dashboard import OWNER_DASHBOARD_HTML


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


class WorkforceRoutePreviewInput(BaseModel):
    department: str = Field(min_length=1, max_length=80)
    required_capabilities: list[str] = Field(min_length=1, max_length=20)
    limit: int = Field(default=5, ge=1, le=10)


class AgentStateChangeInput(BaseModel):
    target_state: AgentState
    expected_revision: int = Field(ge=1)


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


@app.get("/owner", response_class=HTMLResponse)
def owner_dashboard() -> HTMLResponse:
    response = HTMLResponse(OWNER_DASHBOARD_HTML)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "opencompany-core", "mode": "owner-authenticated"}


@app.get("/workforce/roles")
def workforce_roles() -> dict:
    roles = default_workforce().all()
    return {
        "catalogue": "opencompany-original",
        "count": len(roles),
        "specialist_count": sum(1 for role in roles if "__" in role.key),
        "leadership_role_count": sum(1 for role in roles if "__" not in role.key),
        "team_count": len({role.team_key for role in roles if "__" in role.key}),
        "roles": [
            {
                "key": role.key, "title": role.title, "function": role.function, "team_key": role.team_key,
                "mission": role.mission, "capabilities": list(role.capabilities),
                "permitted_outputs": list(role.permitted_outputs),
                "prohibited_actions": list(role.prohibited_actions),
            }
            for role in roles
        ],
    }


@app.post("/workforce/route-preview")
def workforce_route_preview(payload: WorkforceRoutePreviewInput) -> dict:
    try:
        default_organization().get(payload.department)
        matches = default_workforce().match_in_department(
            payload.department, payload.required_capabilities
        )[:payload.limit]
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    requested = {value.strip().casefold() for value in payload.required_capabilities}
    return {
        "department": payload.department,
        "required_capabilities": payload.required_capabilities,
        "candidate_count": len(matches),
        "candidates": [
            {
                "role_key": role.key,
                "title": role.title,
                "team_key": role.team_key,
                "matched_capabilities": [
                    capability for capability in role.capabilities
                    if capability.casefold() in requested
                ],
                "capabilities": list(role.capabilities),
            }
            for role in matches
        ],
        "assignment_performed": False,
        "execution_started": False,
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


@app.get("/providers/status")
def provider_runtime_status() -> dict:
    api_key = os.environ.get("OPENCOMPANY_OPENROUTER_API_KEY", "").strip()
    model = os.environ.get("OPENCOMPANY_OPENROUTER_FREE_MODEL", "").strip()
    confirmation = os.environ.get("OPENCOMPANY_CONFIRM_OPENROUTER_FREE", "").strip().lower()
    configured = bool(api_key and model.endswith(":free") and confirmation == "true")
    partial = bool(api_key or model or confirmation) and not configured
    return {
        "gateway_enabled": configured,
        "provider": "openrouter" if configured else None,
        "model": model if configured else None,
        "billing_mode": "free_confirmed" if configured else "disabled",
        "partial_configuration_detected": partial,
        "real_inference_verified": False,
        "paid_fallback": False,
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


@app.get("/agents", dependencies=[Depends(require_owner_key)])
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


@app.post("/agents/{agent_id}/state", dependencies=[Depends(require_owner_key)])
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


@app.post("/agents/bootstrap", dependencies=[Depends(require_owner_key)])
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


@app.post("/agents/bootstrap-executive", dependencies=[Depends(require_owner_key)])
def bootstrap_executive(store: SQLiteStore = Depends(get_store)) -> dict:
    agent = bootstrap_executive_orchestrator(store)
    return {
        "count": 1,
        "agent": {"id": str(agent.id), "name": agent.name,
                  "department": agent.department, "state": agent.state.value},
        "execution_started": False,
    }


@app.post("/agents/bootstrap-specialists", dependencies=[Depends(require_owner_key)])
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
