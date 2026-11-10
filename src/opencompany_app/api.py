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

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
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
from opencompany_core.unorouter_adapter import unorouter_configuration_status
from opencompany_core.provisioning import bootstrap_department_managers, bootstrap_specialist_profiles, bootstrap_executive_orchestrator
from opencompany_core.manager_orchestration import plan_department_work
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.worker_queue import QueueError
from opencompany_app.runtime import OpenCompanyRuntime, create_runtime
from opencompany_app.dashboard import OWNER_DASHBOARD_HTML


app = FastAPI(
    title="OpenCompany Core",
    version="0.2.0",
    description="Owner-authenticated API for OpenCompany's independently authored operating core.",
)


class OwnerLoginInput(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


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


class DelegationPreviewInput(BaseModel):
    required_capabilities: list[str] = Field(min_length=1, max_length=20)
    max_specialists: int = Field(default=5, ge=1, le=5)


class WorkItemTransitionInput(BaseModel):
    target_state: TaskState


class WorkItemReviewInput(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)


@lru_cache(maxsize=1)
def _default_runtime() -> OpenCompanyRuntime:
    return create_runtime()


def get_runtime() -> OpenCompanyRuntime:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_runtime()


def get_delegation_store() -> DelegationRepository:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_runtime().delegations


def get_store() -> SQLiteStore:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_runtime().store


def require_owner_key(
    request: Request,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    x_opencompany_api_key: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
    opencompany_session: str | None = Cookie(default=None),
) -> str:
    expected = os.environ.get("OPENCOMPANY_OWNER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    if opencompany_session:
        mutating = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
        if runtime.sessions.validate(
            opencompany_session, x_csrf_token, require_csrf=mutating
        ):
            return "owner"
    if x_opencompany_api_key and hmac.compare_digest(x_opencompany_api_key, expected):
        return "owner"
    raise HTTPException(status_code=401, detail="Owner authentication failed.")


def _record(item: WorkItem, action: str) -> AuditRecord:
    from datetime import datetime, timezone

    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type="work_item", subject_id=str(item.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={"state": item.state.value, "department": item.department},
    )


@app.post("/auth/session")
def create_owner_session(
    payload: OwnerLoginInput,
    response: Response,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Exchange the owner API key for a revocable HttpOnly session cookie."""
    expected = os.environ.get("OPENCOMPANY_OWNER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner authentication is not configured.")
    if not hmac.compare_digest(payload.api_key, expected):
        raise HTTPException(status_code=401, detail="Owner authentication failed.")
    token, csrf, expires = runtime.sessions.create(lifetime_hours=12)
    secure_cookie = os.environ.get("OPENCOMPANY_COOKIE_SECURE", "true").strip().lower() == "true"
    response.set_cookie(
        "opencompany_session", token, max_age=12 * 60 * 60, httponly=True,
        secure=secure_cookie, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "csrf_token": csrf, "expires_at": expires.isoformat()}


@app.get("/auth/session", dependencies=[Depends(require_owner_key)])
def owner_session_status() -> dict:
    return {"authenticated": True, "session_type": "owner"}


@app.post("/auth/logout", dependencies=[Depends(require_owner_key)])
def revoke_owner_session(
    request: Request,
    response: Response,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    opencompany_session: str | None = Cookie(default=None),
) -> dict:
    if opencompany_session:
        runtime.sessions.revoke(opencompany_session)
    response.delete_cookie("opencompany_session", path="/", httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False, "revoked": bool(opencompany_session)}


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
    # Credentials are never returned. UnoRouter is a first-class company provider;
    # OpenRouter remains an optional independent provider.
    uno = unorouter_configuration_status()
    openrouter_key = os.environ.get("OPENCOMPANY_OPENROUTER_API_KEY", "").strip()
    openrouter_model = os.environ.get("OPENCOMPANY_OPENROUTER_FREE_MODEL", "").strip()
    openrouter_confirm = os.environ.get("OPENCOMPANY_CONFIRM_OPENROUTER_FREE", "").strip().lower()
    openrouter_configured = bool(
        openrouter_key and openrouter_model.endswith(":free") and openrouter_confirm == "true"
    )
    openrouter_partial = bool(openrouter_key or openrouter_model or openrouter_confirm) and not openrouter_configured
    providers = {
        "unorouter": uno,
        "openrouter": {
            "configured": openrouter_configured,
            "model": openrouter_model if openrouter_configured else None,
            "billing_mode": "free_confirmed" if openrouter_configured else "disabled",
            "partial_configuration_detected": openrouter_partial,
            "automatic_paid_fallback": False,
        },
    }
    active = next((name for name, state in providers.items() if state["configured"]), None)
    return {
        "gateway_enabled": active is not None,
        "provider": active,
        "model": providers[active]["model"] if active else None,
        "billing_mode": "free_confirmed" if active else "disabled",
        "providers": providers,
        "partial_configuration_detected": any(
            state["partial_configuration_detected"] for state in providers.values()
        ),
        "real_inference_verified": False,
        "paid_fallback": False,
    }


@app.get("/providers/candidates")
def provider_candidates() -> dict:
    items = free_provider_candidates()
    uno_configured = unorouter_configuration_status()["configured"]
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
                "configured": bool(uno_configured) if item.key == "unorouter-free-models" else False,
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
                "assigned_agent_id": str(item.assigned_agent_id) if item.assigned_agent_id else None,
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


@app.post("/work-items/{item_id}/enqueue", dependencies=[Depends(require_owner_key)])
def enqueue_work_item(
    item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner explicitly admits an approved, assigned READY task to the durable queue."""
    from datetime import datetime, timezone

    item = runtime.store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    if item.state != TaskState.READY or item.assigned_agent_id is None:
        raise HTTPException(status_code=409, detail="Only READY tasks with an explicit assignee can be queued.")
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
    if agent.role_key not in department.role_keys or role.team_key != agent.team_key:
        raise HTTPException(status_code=409, detail="Assigned agent role or team does not match the department catalogue.")
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action="work_item.queued",
        subject_type="work_item", subject_id=str(item.id), outcome="recorded",
        correlation_id=str(uuid4()),
        details={"agent_id": str(agent.id), "role_key": agent.role_key, "team_key": agent.team_key},
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


@app.get("/workers/queue", dependencies=[Depends(require_owner_key)])
def worker_queue_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    counts = runtime.queue.counts()
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "worker_process_autostarted": False,
        "execution_requires_explicit_worker_process": True,
    }


@app.get("/workers/status", dependencies=[Depends(require_owner_key)])
def worker_fleet_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    status = runtime.fleet.status()
    return {
        "running": status.running,
        "completed_cycles": status.completed_cycles,
        "idle_cycles": status.idle_cycles,
        "failed_cycles": status.failed_cycles,
        "active_agent_profiles": sum(
            1 for agent in runtime.store.list_agents(limit=1000)
            if agent.state == AgentState.ACTIVE and agent.role_key
        ),
    }


@app.post("/workers/start", dependencies=[Depends(require_owner_key)])
def start_worker_fleet(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    started = runtime.fleet.start()
    return {"running": runtime.fleet.status().running, "started_now": started}


@app.post("/workers/stop", dependencies=[Depends(require_owner_key)])
def stop_worker_fleet(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    stopped = runtime.fleet.stop(timeout_seconds=10.0)
    return {"running": runtime.fleet.status().running, "stopped_now": stopped}


@app.post("/workers/{agent_id}/run-once", dependencies=[Depends(require_owner_key)])
def run_agent_once(
    agent_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-trigger one bounded internal worker cycle for one active profile."""
    agent = runtime.store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    if agent.state != AgentState.ACTIVE or not agent.role_key:
        raise HTTPException(status_code=409, detail="Agent must be explicitly ACTIVE with a role.")
    try:
        result = runtime.worker.run_once(agent.id, agent.role_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Worker cycle failed: {type(exc).__name__}") from exc
    return {"agent_id": str(agent.id), "role_key": agent.role_key, "result": result}


@app.post("/work-items/{item_id}/delegation-preview", dependencies=[Depends(require_owner_key)])
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

    
@app.post("/work-items/{item_id}/delegation-proposals", dependencies=[Depends(require_owner_key)])
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
    try:
        plan = plan_department_work(item, payload.required_capabilities, max_specialists=payload.max_specialists)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profiles = store.list_agents(limit=1000)
    manager = next((agent for agent in profiles if agent.role_key == plan.manager_role_key and agent.department == item.department), None)
    if manager is None:
        raise HTTPException(status_code=409, detail="Provision department manager profiles before creating a delegation proposal.")
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
            if profile is None:
                raise HTTPException(status_code=409, detail=f"Specialist profile is not provisioned: {specialist.role_key}")
            children.append({
                "assigned_agent_id": str(profile.id), "role_key": specialist.role_key,
                "team_key": specialist.team_key, "title": f"{specialist.title}: {item.title}",
                "objective": f"Support parent work item {item.id}. Parent objective: {item.objective} Required capabilities: {', '.join(payload.required_capabilities)}. Produce an internal draft for manager review only.",
            })
    return delegations.create_proposal(
        parent_work_item_id=item.id,
        request={"required_capabilities": payload.required_capabilities, "max_specialists": payload.max_specialists},
        manager_agent_id=manager.id,
        mode=plan.mode.value,
        team_key=plan.selected_team_key,
        children=children,
    )


@app.post("/work-items/{item_id}/delegation-proposals/{proposal_id}/approve", dependencies=[Depends(require_owner_key)])
def approve_work_item_delegation_proposal(
    item_id: UUID, proposal_id: UUID,
    store: SQLiteStore = Depends(get_store),
    delegations: DelegationRepository = Depends(get_delegation_store),
) -> dict:
    """Owner approval materializes child tasks as READY; it never queues them."""
    from datetime import datetime, timezone

    parent = store.get_work_item(item_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent work item not found.")
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
    try:
        saved = store.approve_delegation_proposal(proposal_id, tuple(tasks), tuple(events))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not saved:
        raise HTTPException(status_code=409, detail="Proposal was approved or changed concurrently.")
    return {
        "proposal_id": str(proposal_id), "status": "approved",
        "materialized_work_items": [
            {"id": str(task.id), "assigned_agent_id": str(task.assigned_agent_id),
             "state": task.state.value} for task in tasks
        ],
        "queue_entries_created": False, "execution_started": False,
    }


@app.get("/work-items/{item_id}/delegation-proposals", dependencies=[Depends(require_owner_key)])
def list_work_item_delegation_proposals(
    item_id: UUID,
    store: SQLiteStore = Depends(get_store),
    delegations: DelegationRepository = Depends(get_delegation_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    proposals = delegations.list_for_parent(item_id)
    return {"count": len(proposals), "proposals": proposals}


@app.post("/work-items/{item_id}/review", dependencies=[Depends(require_owner_key)])
def review_work_item(
    item_id: UUID, payload: WorkItemReviewInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    from datetime import datetime, timezone

    action = "work_item.review_approved" if payload.approved else "work_item.review_rejected"
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action=action, subject_type="work_item",
        subject_id=str(item_id), outcome="recorded", correlation_id=str(uuid4()),
        details={"approved": payload.approved, "rationale": payload.rationale},
    )
    try:
        state = store.review_work_item_with_audit(
            item_id, approved=payload.approved, rationale=payload.rationale, record=event,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if state is None:
        raise HTTPException(status_code=409, detail="Work item is not awaiting review.")
    return {"item_id": str(item_id), "state": state.value, "approved": payload.approved}

@app.post("/work-items/{item_id}/transition", dependencies=[Depends(require_owner_key)])
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
    if payload.target_state in {TaskState.QUEUED, TaskState.IN_PROGRESS}:
        raise HTTPException(status_code=409, detail="Use owner queue admission and the worker claim pipeline for execution states.")
    known = {value.id: value for value in store.list_work_items(limit=1000)}
    try:
        changed = transition_work_item(item, payload.target_state, known_items=known)
    except StateTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_work_item_with_audit(changed, _record(changed, "work_item.state_changed"))
    return {"item_id": str(changed.id), "state": changed.state.value}


@app.get("/work-items/{item_id}/deliverables", dependencies=[Depends(require_owner_key)])
def list_work_item_deliverables(
    item_id: UUID, store: SQLiteStore = Depends(get_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    artifacts = store.list_deliverables(item_id)
    return {"count": len(artifacts), "deliverables": artifacts}


@app.get("/audit/verify", dependencies=[Depends(require_owner_key)])
def verify_audit(store: SQLiteStore = Depends(get_store)) -> dict:
    return {
        "event_count": store.audit_event_count(),
        "chain_valid": store.verify_audit_chain(),
    }
