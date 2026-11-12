"""Standalone OpenCompany API, independent of legacy AIOS modules.

The service exposes a public read-only health check. Company records and
write operations require owner authentication. Model calls are cost-gated to explicitly configured free providers; external business actions remain outside the runtime's authority.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import replace
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

from opencompany_core.platform import PLATFORM_ID, PLATFORM_NAME, PLATFORM_VERSION
from opencompany_core.domain import BUSINESS_UNIT_IDS, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore
from opencompany_core.planning import PlanError, WorkPlan, action_requires_owner_approval
from opencompany_core.workforce import default_workforce
from opencompany_core.organization import default_organization
from opencompany_core.provider_catalog import free_provider_candidates
from opencompany_core.unorouter_adapter import (
    unorouter_configuration_status,
)
from opencompany_core.secret_vault import SecretVaultError
from opencompany_app.provider_settings_ui import OWNER_PROVIDER_SETTINGS_HTML, OWNER_PROVIDER_SETTINGS_JS
from opencompany_core.provisioning import bootstrap_department_managers, bootstrap_specialist_profiles, bootstrap_executive_orchestrator
from opencompany_core.manager_orchestration import plan_department_work
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.worker_queue import QueueError
from opencompany_core.manager_ai import ManagerPlanningError, recommend_department_plan
from opencompany_core.executive_ai import ExecutivePlanningError, create_executive_plan
from opencompany_core.model_gateway import CostPolicyViolation, ModelRequest, NoEligibleProvider, ProviderUnavailable
from opencompany_core.collaboration import AgentHandoff, HandoffState, accept_handoff, decline_handoff, deliver_handoff
from opencompany_core.learning import ImprovementProposal, OutcomeEvaluation, OutcomeGrade, ProposalState
from opencompany_app.api_schemas import (
    UnoRouterDiscoveryInput,
    PlanItemInput,
    PlanPreviewInput,
    WorkItemCreateInput,
    DelegationPreviewInput,
    OutcomeEvaluationInput,
    LearningAIProposalInput,
    ImprovementProposalInput,
    LearningDecisionInput,
    LearningNoteInput,
    HandoffCreateInput,
    HandoffDeliverInput,
    ExecutivePlanInput,
    ManagerProposalInput,
)
from opencompany_app.api_dependencies import (
    _default_runtime,
    get_delegation_store,
    get_optional_runtime,
    get_runtime,
    get_store,
    require_owner_key,
)
from opencompany_app.routers.catalogue import router as catalogue_router
from opencompany_app.routers.system import router as system_router
from opencompany_app.routers.providers import router as providers_router, _worker_autostart_enabled
from opencompany_app.routers.github_evolution import settings_router as github_settings_router, evolution_router as github_evolution_router
from opencompany_app.routers.integrations import router as integrations_router
from opencompany_app.routers.agents import router as agents_router
from opencompany_app.routers.commercial import router as commercial_router, supplier_router as commercial_supplier_router
from opencompany_app.routers.workers import router as workers_router
from opencompany_app.routers.work_items import router as work_items_router
from opencompany_app.routers.handoffs import router as handoffs_router
from opencompany_app.routers.orchestration import router as orchestration_router
from opencompany_app.routers.lifecycle import router as lifecycle_router
from opencompany_app.routers.learning import router as learning_router
from opencompany_app.routers.portfolio import router as portfolio_router
from opencompany_app.routers.auth import router as auth_router
from opencompany_app.routers.operations import backup_router as operations_backup_router, diagnostics_router as operations_diagnostics_router
from opencompany_app.runtime import OpenCompanyRuntime
from opencompany_app.dashboard import OWNER_DASHBOARD_HTML


app = FastAPI(
    title=PLATFORM_NAME,
    version=PLATFORM_VERSION,
    description="Unified OpenCompany AIOS platform: one independently authored engine, company runtime, and owner console.",
)

# Per-process login throttling. The API key is a bootstrap credential; this
# protects the session exchange endpoint from unlimited online guessing.
_LOGGER = logging.getLogger(__name__)


@app.on_event("startup")
def initialize_autonomous_runtime() -> None:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        return
    bootstrap_enabled = os.environ.get("OPENCOMPANY_BOOTSTRAP_WORKFORCE", "false").casefold() == "true"
    activate_enabled = os.environ.get("OPENCOMPANY_AUTO_ACTIVATE_WORKFORCE", "false").casefold() == "true"
    autostart_enabled = _worker_autostart_enabled()
    if not (bootstrap_enabled or activate_enabled or autostart_enabled):
        return
    runtime = _default_runtime()
    if bootstrap_enabled:
        bootstrap_department_managers(runtime.store)
        bootstrap_specialist_profiles(runtime.store)
        bootstrap_executive_orchestrator(runtime.store)
    if activate_enabled:
        runtime.store.activate_all_draft_agents_with_audit()
    # Autostart is an explicit owner-controlled deployment setting. The gateway
    # still enforces the live strict-free catalogue and a zero-dollar request
    # budget for every inference call; unavailable free models fail closed.
    if autostart_enabled:
        try:
            if runtime.gateway.eligible_providers(request_budget_usd=0.0):
                runtime.fleet.start()
            else:
                _LOGGER.warning("Worker autostart was requested but no confirmed-free provider is configured.")
        except Exception:
            _LOGGER.exception("Worker autostart could not initialize safely; workers remain stopped.")


@app.on_event("shutdown")
def close_autonomous_runtime() -> None:
    if _default_runtime.cache_info().currsize:
        _default_runtime().close()
        _default_runtime.cache_clear()


@app.get("/owner", response_class=HTMLResponse)
def owner_dashboard() -> HTMLResponse:
    html = OWNER_DASHBOARD_HTML.replace("</main>", OWNER_PROVIDER_SETTINGS_HTML + "\n</main>")
    before, marker, after = html.rpartition("})();")
    if marker:
        html = before + OWNER_PROVIDER_SETTINGS_JS + "\n  const previousLoad=load; load=async function(){await previousLoad(); await loadUnoRouterSettings(); await loadGitHubEvolutionSettings(); await loadModelUsage();};\n})();" + after
    # The dashboard currently embeds its scripts. Give every script element a
    # fresh nonce rather than allowing arbitrary inline script execution.
    nonce = secrets.token_urlsafe(18)
    html = re.sub(r"<script(?=[\s>])", f'<script nonce="{nonce}"', html)
    html = re.sub(r"<style(?=[\s>])", f'<style nonce="{nonce}"', html)
    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'nonce-{nonce}'; connect-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'; object-src 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response



app.include_router(system_router)
app.include_router(operations_backup_router)


app.include_router(catalogue_router)


@app.get("/providers/status")
def provider_runtime_status(runtime: OpenCompanyRuntime | None = Depends(get_optional_runtime)) -> dict:
    # Credentials are never returned. Saved owner settings take precedence over legacy env configuration.
    try:
        saved_uno = runtime.secret_vault.get("unorouter") if runtime is not None else None
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored UnoRouter settings cannot be decrypted; check the server encryption key.") from exc
    uno = unorouter_configuration_status({
        "api_key": saved_uno["api_key"], "model": saved_uno["model"], "confirmed_free": "true"
    }) if saved_uno else unorouter_configuration_status()
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
        "real_inference_verified": runtime.unorouter_tested_at is not None if runtime is not None else False,
        "paid_fallback": False,
    }




app.include_router(providers_router)

app.include_router(github_settings_router)




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


app.include_router(agents_router)
app.include_router(commercial_router)


app.include_router(work_items_router)


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


app.include_router(workers_router)


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

    
app.include_router(integrations_router)


app.include_router(github_evolution_router)
app.include_router(learning_router)


app.include_router(handoffs_router)


@app.get("/executive/portfolio", dependencies=[Depends(require_owner_key)])
def get_executive_portfolio(
    business_id: str | None = None,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    """Give the owner a company-wide view of CEO and department execution."""
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")

    profiles = store.list_agents(limit=1000)
    ceo = next((agent for agent in profiles
                if agent.role_key == "chief_executive_orchestrator"), None)
    work_items = store.list_work_items(business_id=business_id, limit=1000)
    department_rows: dict[str, dict] = {}
    items_payload = []
    for item in work_items:
        department = default_organization().get(item.department)
        manager = next((agent for agent in profiles
                        if agent.role_key == department.manager_role_key
                        and agent.department == item.department
                        and agent.team_key == "management"), None)
        dependencies = []
        for dependency_id in item.depends_on:
            dependency = store.get_work_item(dependency_id)
            if dependency is None:
                dependencies.append({
                    "work_item_id": str(dependency_id), "state": "missing",
                    "completed_with_deliverable": False,
                })
                continue
            if dependency.business_id != item.business_id:
                raise HTTPException(status_code=409, detail="Work dependency crossed a business boundary.")
            dependency_deliverables = store.list_deliverables(dependency_id)
            dependencies.append({
                "work_item_id": str(dependency_id), "state": dependency.state.value,
                "deliverable_count": len(dependency_deliverables),
                "completed_with_deliverable": (
                    dependency.state == TaskState.COMPLETED and bool(dependency_deliverables)
                ),
            })
        manager_ready = (
            item.state == TaskState.READY
            and bool(item.depends_on)
            and manager is not None
            and manager.state == AgentState.ACTIVE
            and item.assigned_agent_id == manager.id
            and all(value["completed_with_deliverable"] for value in dependencies)
        )
        deliverables = store.list_deliverables(item.id)
        row = {
            "id": str(item.id), "title": item.title, "objective": item.objective,
            "business_id": item.business_id, "department": item.department,
            "state": item.state.value,
            "assigned_agent_id": str(item.assigned_agent_id) if item.assigned_agent_id else None,
            "manager": ({
                "agent_id": str(manager.id), "role_key": manager.role_key,
                "state": manager.state.value,
            } if manager else None),
            "dependency_count": len(dependencies),
            "blocked_dependencies": [
                value["work_item_id"] for value in dependencies
                if not value["completed_with_deliverable"]
            ],
            "deliverable_count": len(deliverables),
            "manager_synthesis_ready": manager_ready,
        }
        items_payload.append(row)
        key = f"{item.business_id}:{item.department}"
        aggregate = department_rows.setdefault(key, {
            "business_id": item.business_id, "department": item.department,
            "work_item_count": 0, "states": {}, "blocked_count": 0,
            "review_count": 0, "completed_count": 0,
            "manager_synthesis_ready_count": 0,
        })
        aggregate["work_item_count"] += 1
        aggregate["states"][item.state.value] = aggregate["states"].get(item.state.value, 0) + 1
        aggregate["blocked_count"] += bool(row["blocked_dependencies"])
        aggregate["review_count"] += item.state == TaskState.REVIEW
        aggregate["completed_count"] += item.state == TaskState.COMPLETED
        aggregate["manager_synthesis_ready_count"] += manager_ready

    return {
        "platform": "opencompany-aios",
        "business_filter": business_id or "all",
        "ceo": ({
            "agent_id": str(ceo.id), "state": ceo.state.value,
            "active": ceo.state == AgentState.ACTIVE,
        } if ceo else None),
        "departments": list(department_rows.values()),
        "work_items": items_payload,
        "summary": {
            "work_item_count": len(items_payload),
            "department_count": len(department_rows),
            "blocked_work_item_count": sum(
                1 for item in items_payload if item["blocked_dependencies"]
            ),
            "awaiting_owner_review_count": sum(
                1 for item in items_payload if item["state"] == TaskState.REVIEW.value
            ),
            "completed_work_item_count": sum(
                1 for item in items_payload if item["state"] == TaskState.COMPLETED.value
            ),
            "manager_synthesis_ready_count": sum(
                1 for item in items_payload if item["manager_synthesis_ready"]
            ),
        },
        "execution_or_external_actions_performed": False,
    }


app.include_router(orchestration_router)
app.include_router(lifecycle_router)


app.include_router(commercial_supplier_router)
app.include_router(portfolio_router)
app.include_router(auth_router)
app.include_router(operations_diagnostics_router)

