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
from opencompany_app.routers.planning import planning_router, queue_router, delegation_router
from opencompany_app.routers.provider_info import provider_status_router, provider_candidates_router, executive_portfolio_router
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
app.include_router(provider_status_router)
app.include_router(operations_backup_router)


app.include_router(catalogue_router)


app.include_router(providers_router)

app.include_router(github_settings_router)
app.include_router(provider_candidates_router)




app.include_router(planning_router)
app.include_router(agents_router)
app.include_router(commercial_router)


app.include_router(work_items_router)
app.include_router(queue_router)


app.include_router(workers_router)
app.include_router(delegation_router)


app.include_router(integrations_router)


app.include_router(github_evolution_router)
app.include_router(learning_router)


app.include_router(handoffs_router)


app.include_router(orchestration_router)
app.include_router(lifecycle_router)


app.include_router(commercial_supplier_router)
app.include_router(portfolio_router)
app.include_router(executive_portfolio_router)
app.include_router(auth_router)
app.include_router(operations_diagnostics_router)

