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
from opencompany_core.lifecycle import StateTransitionError, transition_work_item
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
from opencompany_core.venture_portfolio import VenturePortfolio, VenturePortfolioError
from opencompany_app.api_schemas import (
    OwnerLoginInput,
    UnoRouterDiscoveryInput,
    VentureOpportunityInput,
    VentureOpportunityStatusInput,
    PlanItemInput,
    PlanPreviewInput,
    WorkItemCreateInput,
    CommercialOpportunityInput,
    CommercialProductStatusInput,
    CommercialProductInput,
    CommercialQuoteLineInput,
    CommercialQuoteInput,
    CommercialQuoteDecisionInput,
    CommercialOrderStatusInput,
    CommercialOrderInput,
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
    WorkItemTransitionInput,
    WorkItemReviewInput,
    CommercialSupplierInput,
    CommercialSupplierStatusInput,
)
from opencompany_app.api_dependencies import (
    _clear_login_failures,
    _default_runtime,
    _login_retry_after,
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
from opencompany_app.routers.workers import router as workers_router
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


def _record(item: WorkItem, action: str) -> AuditRecord:
    from datetime import datetime, timezone

    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type="work_item", subject_id=str(item.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={
            "state": item.state.value, "department": item.department,
            "business_id": item.business_id,
        },
    )


@app.post("/auth/session")
def create_owner_session(
    payload: OwnerLoginInput,
    request: Request,
    response: Response,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Exchange the owner API key for a revocable HttpOnly session cookie."""
    expected = os.environ.get("OPENCOMPANY_OWNER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner authentication is not configured.")
    client_key = request.client.host if request.client else "unknown"
    retry_after = _login_retry_after(client_key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many failed owner login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    if not hmac.compare_digest(payload.api_key, expected):
        retry_after = _login_retry_after(client_key, failed=True)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Too many failed owner login attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(status_code=401, detail="Owner authentication failed.")
    _clear_login_failures(client_key)
    token, csrf, expires = runtime.sessions.create(lifetime_hours=168)
    secure_cookie = os.environ.get("OPENCOMPANY_COOKIE_SECURE", "true").strip().lower() == "true"
    response.set_cookie(
        "opencompany_session", token, max_age=7 * 24 * 60 * 60, httponly=True,
        secure=secure_cookie, samesite="strict", path="/",
    )
    response.set_cookie(
        "opencompany_csrf", csrf, max_age=7 * 24 * 60 * 60, httponly=True,
        secure=secure_cookie, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "csrf_token": csrf, "expires_at": expires.isoformat()}


@app.get("/auth/session", dependencies=[Depends(require_owner_key)])
def owner_session_status(
    response: Response,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    opencompany_session: str | None = Cookie(default=None),
    opencompany_csrf: str | None = Cookie(default=None),
) -> dict:
    """Restore the same CSRF token across tabs; rotate only if its cookie is missing or invalid."""
    if not opencompany_session:
        raise HTTPException(status_code=401, detail="Owner browser session is missing.")
    renewed = runtime.sessions.rotate_csrf(opencompany_session, opencompany_csrf)
    if renewed is None:
        raise HTTPException(status_code=401, detail="Owner browser session has expired or been revoked.")
    csrf, expires = renewed
    secure_cookie = os.environ.get("OPENCOMPANY_COOKIE_SECURE", "true").strip().lower() == "true"
    response.set_cookie(
        "opencompany_csrf", csrf, max_age=7 * 24 * 60 * 60, httponly=True,
        secure=secure_cookie, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "authenticated": True, "session_type": "owner",
        "csrf_token": csrf, "expires_at": expires.isoformat(),
    }


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
    response.delete_cookie("opencompany_csrf", path="/", httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False, "revoked": bool(opencompany_session)}


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


@app.get("/owner/backup", dependencies=[Depends(require_owner_key)])
def download_owner_database_backup(store: SQLiteStore = Depends(get_store)) -> FileResponse:
    """Download a consistent, integrity-checked SQLite snapshot for owner backup."""
    descriptor, backup_path = tempfile.mkstemp(prefix="opencompany-backup-", suffix=".sqlite3")
    os.close(descriptor)
    try:
        store.backup_to(backup_path)
    except Exception as exc:
        try:
            os.unlink(backup_path)
        except FileNotFoundError:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Database backup failed safely: {type(exc).__name__}",
        ) from exc
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return FileResponse(
        backup_path,
        media_type="application/vnd.sqlite3",
        filename=f"opencompany-backup-{stamp}.sqlite3",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        background=BackgroundTask(os.unlink, backup_path),
    )



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


@app.post("/commercial/opportunities", dependencies=[Depends(require_owner_key)])
def create_commercial_opportunity(
    payload: CommercialOpportunityInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    from datetime import datetime, timezone
    allowed = {"physical-agency", "physical-brand", "digital-products"}
    if payload.business_id not in allowed:
        raise HTTPException(status_code=422, detail="A customer opportunity must select exactly one commercial business unit; core is internal only.")
    if not payload.scope_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that this opportunity covers only the customer's stated need in the selected business.")
    now = datetime.now(timezone.utc).isoformat()
    opportunity_id = str(uuid4())
    record = {
        "id": opportunity_id, "business_id": payload.business_id,
        "customer_name": payload.customer_name.strip(),
        "customer_contact": payload.customer_contact.strip() if payload.customer_contact else None,
        "customer_need": payload.customer_need.strip(), "stage": "new",
        "created_at": now, "updated_at": now,
    }
    try:
        store.create_commercial_opportunity(record, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.opportunity_created",
            subject_type="commercial_opportunity", subject_id=opportunity_id,
            outcome="recorded", correlation_id=str(uuid4()),
            details={"business_id": payload.business_id, "scope_confirmed": True},
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"opportunity_id": opportunity_id, "business_id": payload.business_id, "stage": "new"}


@app.get("/commercial/opportunities", dependencies=[Depends(require_owner_key)])
def list_commercial_opportunities(
    business_id: str | None = None, store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        records = store.list_commercial_opportunities(business_id=business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(records), "opportunities": records}


@app.get("/commercial/opportunities/{opportunity_id}/catalogue", dependencies=[Depends(require_owner_key)])
def list_opportunity_catalogue(
    opportunity_id: UUID, store: SQLiteStore = Depends(get_store)
) -> dict:
    opportunity = store.get_commercial_opportunity(str(opportunity_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Commercial opportunity not found.")
    # The opportunity's immutable business_id is the only allowed catalogue scope.
    products = store.list_commercial_products(
        business_id=opportunity["business_id"], status="active"
    )
    return {
        "opportunity_id": str(opportunity_id),
        "business_id": opportunity["business_id"],
        "count": len(products),
        "products": products,
        "scope_enforced": True,
    }


@app.post("/commercial/products", dependencies=[Depends(require_owner_key)])
def create_commercial_product(
    payload: CommercialProductInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    from datetime import datetime, timezone
    allowed = {"physical-agency", "physical-brand", "digital-products"}
    if payload.business_id not in allowed:
        raise HTTPException(status_code=422, detail="Catalogue entries must belong to one commercial business unit; core is internal only.")
    now = datetime.now(timezone.utc).isoformat()
    product_id = str(uuid4())
    record = {
        "id": product_id, "business_id": payload.business_id,
        "name": payload.name.strip(), "description": payload.description.strip(),
        "category": payload.category.strip(), "status": "draft",
        "created_at": now, "updated_at": now,
    }
    try:
        store.create_commercial_product(record, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.product_created",
            subject_type="commercial_product", subject_id=product_id,
            outcome="draft", correlation_id=str(uuid4()),
            details={"business_id": payload.business_id, "status": "draft"},
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"product_id": product_id, "business_id": payload.business_id, "status": "draft", "published": False}


@app.post("/commercial/products/{product_id}/status", dependencies=[Depends(require_owner_key)])
def update_commercial_product_status(
    product_id: UUID, payload: CommercialProductStatusInput,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    from datetime import datetime, timezone
    if payload.status not in {"active", "archived"}:
        raise HTTPException(status_code=422, detail="Status must be active or archived.")
    if not payload.confirm_owner_approval:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to change catalogue status.")
    changed = store.update_commercial_product_status(
        str(product_id), payload.status, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner",
            action="commercial.product_status_changed",
            subject_type="commercial_product", subject_id=str(product_id),
            outcome=payload.status, correlation_id=str(uuid4()),
            details={"status": payload.status, "owner_confirmed": True},
        )
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Product not found or already archived.")
    return {"product_id": str(product_id), "status": payload.status, "published": False}


@app.get("/commercial/products", dependencies=[Depends(require_owner_key)])
def list_commercial_products(
    business_id: str | None = None, status: str | None = None,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        records = store.list_commercial_products(business_id=business_id, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(records), "products": records}


@app.post("/commercial/quotes", dependencies=[Depends(require_owner_key)])
def create_commercial_quote(
    payload: CommercialQuoteInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    currency = payload.currency.upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise HTTPException(status_code=422, detail="Currency must be a three-letter ISO code.")
    if payload.currency_exponent not in {0, 2, 3}:
        raise HTTPException(status_code=422, detail="Currency exponent must be 0, 2, or 3.")
    opportunity = store.get_commercial_opportunity(str(payload.opportunity_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Commercial opportunity not found.")
    subtotal = sum(item.quantity * item.unit_price_minor for item in payload.items)
    if subtotal <= 0 or subtotal > 9_000_000_000_000_000:
        raise HTTPException(status_code=422, detail="Quote total is outside the supported range.")
    now = datetime.now(timezone.utc).isoformat()
    quote_id = str(uuid4())
    record = {
        "id": quote_id, "opportunity_id": str(payload.opportunity_id),
        "business_id": opportunity["business_id"], "title": payload.title.strip(),
        "currency": currency, "currency_exponent": payload.currency_exponent,
        "subtotal_minor": subtotal, "terms": payload.terms.strip(),
        "created_at": now, "updated_at": now,
    }
    items = [{
        "id": str(uuid4()), "product_id": str(item.product_id),
        "description": item.description.strip(), "quantity": item.quantity,
        "unit_price_minor": item.unit_price_minor,
    } for item in payload.items]
    try:
        result = store.create_commercial_quote(record, items, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.quote_created",
            subject_type="commercial_quote", subject_id=quote_id, outcome="draft",
            correlation_id=str(uuid4()),
            details={"business_id": opportunity["business_id"], "opportunity_id": str(payload.opportunity_id),
                     "currency": currency, "currency_exponent": payload.currency_exponent,
                     "subtotal_minor": subtotal},
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"quote_id": quote_id, **result, "sent": False}


@app.get("/commercial/quotes", dependencies=[Depends(require_owner_key)])
def list_commercial_quotes(
    opportunity_id: UUID | None = None, business_id: str | None = None,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        quotes = store.list_commercial_quotes(
            opportunity_id=str(opportunity_id) if opportunity_id else None,
            business_id=business_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(quotes), "quotes": quotes}


@app.post("/commercial/quotes/{quote_id}/decision", dependencies=[Depends(require_owner_key)])
def decide_commercial_quote(
    quote_id: UUID, payload: CommercialQuoteDecisionInput,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    if not payload.confirm_owner_decision:
        raise HTTPException(status_code=422, detail="Owner confirmation is required.")
    if payload.status not in {"approved_for_delivery", "accepted", "rejected", "void"}:
        raise HTTPException(status_code=422, detail="Unsupported quote decision.")
    if payload.status == "accepted" and not (payload.acceptance_reference and payload.acceptance_reference.strip()):
        raise HTTPException(status_code=422, detail="Record a customer acceptance evidence reference before marking accepted.")
    try:
        changed = store.update_commercial_quote_status(
            str(quote_id), payload.status, payload.acceptance_reference.strip() if payload.acceptance_reference else None,
            AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                actor_type="owner", actor_id="owner", action="commercial.quote_status_changed",
                subject_type="commercial_quote", subject_id=str(quote_id), outcome=payload.status,
                correlation_id=str(uuid4()),
                details={"status": payload.status, "owner_confirmed": True,
                         "acceptance_evidence_recorded": bool(payload.acceptance_reference)},
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="Quote not found.")
    return {"quote_id": str(quote_id), "status": payload.status, "sent": False}


@app.post("/commercial/orders", dependencies=[Depends(require_owner_key)])
def create_commercial_order(
    payload: CommercialOrderInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    if not payload.confirm_owner_order_record:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to create an order record.")
    order_id = str(uuid4())
    try:
        result = store.create_commercial_order(order_id, str(payload.quote_id), AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.order_recorded",
            subject_type="commercial_order", subject_id=order_id, outcome="awaiting_owner_fulfilment",
            correlation_id=str(uuid4()), details={"quote_id": str(payload.quote_id), "owner_confirmed": True},
        ))
    except ValueError as exc:
        if "already exists for this quote" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="An order already exists for this quote.") from exc
        raise
    return result


@app.post("/commercial/orders/{order_id}/status", dependencies=[Depends(require_owner_key)])
def update_commercial_order_status(
    order_id: UUID, payload: CommercialOrderStatusInput,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    if not payload.confirm_owner_status:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to update order status.")
    if payload.status not in {"in_progress", "fulfilled", "cancelled"}:
        raise HTTPException(status_code=422, detail="Unsupported order status.")
    try:
        changed = store.update_commercial_order_status(
            str(order_id), payload.status, AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                actor_type="owner", actor_id="owner", action="commercial.order_status_changed",
                subject_type="commercial_order", subject_id=str(order_id), outcome=payload.status,
                correlation_id=str(uuid4()),
                details={"status": payload.status, "owner_confirmed": True,
                         "external_fulfilment_triggered": False},
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="Order not found.")
    return {"order_id": str(order_id), "status": payload.status, "external_fulfilment_triggered": False}


@app.get("/commercial/orders", dependencies=[Depends(require_owner_key)])
def list_commercial_orders(
    business_id: str | None = None, store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        orders = store.list_commercial_orders(business_id=business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(orders), "orders": orders}


@app.get("/work-items", dependencies=[Depends(require_owner_key)])
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


@app.post("/work-items", dependencies=[Depends(require_owner_key)])
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
    store.save_work_item_with_audit(item, _record(item, "work_item.created"))
    return {"item_id": str(item.id), "state": item.state.value, "business_id": item.business_id}


def _auto_queue_approved_work_enabled() -> bool:
    return os.environ.get("OPENCOMPANY_AUTO_QUEUE_APPROVED_WORK", "false").strip().casefold() in {"1", "true", "yes", "on"}


def _free_provider_ready(runtime: OpenCompanyRuntime) -> bool:
    return bool(runtime.gateway.eligible_providers(request_budget_usd=0.0))


def _auto_queue_task(runtime: OpenCompanyRuntime, task: WorkItem, agent, *, action: str) -> None:
    from datetime import datetime, timezone

    if agent is None or agent.state != AgentState.ACTIVE or agent.department != task.department:
        raise QueueError("automatic queueing requires an active assignee in the task department")
    department = default_organization().get(task.department)
    role = default_workforce().get(agent.role_key)
    expected_team = (
        "executive" if agent.role_key == "chief_executive_orchestrator"
        else "management" if agent.role_key == department.manager_role_key
        else role.team_key
    )
    if agent.role_key not in department.role_keys or agent.team_key != expected_team:
        raise QueueError("automatic queueing rejected an unverified role/team assignment")
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="system", actor_id="opencompany-auto-queue",
        action=action, subject_type="work_item", subject_id=str(task.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={"agent_id": str(agent.id), "role_key": agent.role_key,
                 "team_key": agent.team_key, "business_id": task.business_id,
                 "request_budget_usd": 0.0},
    )
    runtime.queue.enqueue_authorized(
        task, agent.id, {"role_key": agent.role_key, "team_key": agent.team_key}, event,
    )


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


@app.post("/work-items/{item_id}/evaluations", dependencies=[Depends(require_owner_key)])
def create_outcome_evaluation(
    item_id: UUID,
    payload: OutcomeEvaluationInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    evaluation = OutcomeEvaluation(
        id=uuid4(), work_item_id=item_id, evaluator="owner",
        grade=payload.grade, rubric_scores=payload.rubric_scores,
        evidence_refs=tuple(payload.evidence_refs), observations=payload.observations,
    )
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.outcome_evaluated", subject_type="work_item",
        subject_id=str(item_id), outcome=evaluation.grade.value,
        correlation_id=str(uuid4()),
        details={"evaluation_id": str(evaluation.id), "rubric_scores": dict(evaluation.rubric_scores)},
    )
    try:
        runtime.learning.save_evaluation(evaluation, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": str(evaluation.id), "work_item_id": str(item_id),
        "grade": evaluation.grade.value, "rubric_scores": dict(evaluation.rubric_scores),
        "evidence_refs": list(evaluation.evidence_refs),
        "observations": evaluation.observations, "evaluated_at": evaluation.evaluated_at.isoformat(),
    }


@app.get("/work-items/{item_id}/evaluations", dependencies=[Depends(require_owner_key)])
def list_outcome_evaluations(
    item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    rows = runtime.learning.list_evaluations(item_id)
    return {"count": len(rows), "evaluations": rows}


@app.post("/learning/proposals", dependencies=[Depends(require_owner_key)])
def create_learning_proposal(
    payload: ImprovementProposalInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    proposal = ImprovementProposal(
        id=uuid4(), target=payload.target, change_summary=payload.change_summary,
        rationale=payload.rationale, expected_measurement=payload.expected_measurement,
        risk_level=payload.risk_level, based_on_evaluations=tuple(payload.based_on_evaluations),
        state=ProposalState.PROPOSED,
    )
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.improvement_proposed", subject_type="improvement_proposal",
        subject_id=str(proposal.id), outcome="proposed", correlation_id=str(uuid4()),
        details={"target": proposal.target, "risk_level": proposal.risk_level},
    )
    try:
        runtime.learning.save_proposal(proposal, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": str(proposal.id), "state": proposal.state.value, "owner_decision_required": True}


@app.post("/learning/ai-proposals", dependencies=[Depends(require_owner_key)])
def create_ai_learning_proposal(
    payload: LearningAIProposalInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    all_evaluations = runtime.learning.list_evaluations()
    by_id = {row["id"]: row for row in all_evaluations}
    selected = [by_id.get(str(value)) for value in payload.evaluation_ids]
    if any(item is None for item in selected):
        raise HTTPException(status_code=404, detail="One or more evaluation records were not found.")
    evidence_context = []
    supported_roles = set()
    for evaluation in selected:
        deliverables = store.list_deliverables(UUID(evaluation["work_item_id"]))
        by_deliverable = {item["id"]: item for item in deliverables}
        excerpts = []
        for ref in evaluation["evidence_refs"]:
            if ref.startswith("deliverable:"):
                artifact = by_deliverable.get(ref.split(":", 1)[1])
                if artifact:
                    supported_roles.add(artifact["role_key"])
                    excerpts.append({
                        "role_key": artifact["role_key"],
                        "content_excerpt": artifact["content"][:1800],
                    })
        evidence_context.append({
            "evaluation": evaluation,
            "deliverables": excerpts,
        })
    if len({item["business_id"] for item in selected}) != 1:
        raise HTTPException(status_code=409, detail="Learning analysis cannot combine evidence from different business units.")
    if not supported_roles:
        raise HTTPException(status_code=409, detail="Selected evaluations must cite deliverables with identifiable role keys.")
    business_id = selected[0]["business_id"]
    prompt = (
        "OPENCOMPANY EVIDENCE-BASED LEARNING REVIEW\n"
        f"Business unit: {business_id}. Use only evidence from this business unit.\n"
        "Recommend one narrowly scoped role-learning note based only on the supplied owner evaluations and artifacts. "
        "Do not claim a permanent code change. Return only JSON with exactly these keys: role_key, note, rationale, "
        "expected_measurement, risk_level. The role_key must be one of the supplied roles. The note should be a concise "
        "operating improvement that can be inserted into that role's future prompt only after owner approval.\n"
        f"Supported role keys: {json.dumps(sorted(supported_roles))}\n"
        f"Evidence: {json.dumps(evidence_context, ensure_ascii=False)}"
    )
    try:
        model_result = runtime.gateway.complete(
            ModelRequest(
                prompt=prompt, request_id=str(uuid4()), max_output_tokens=1800,
                business_id=business_id,
            ),
            request_budget_usd=0.0, preferred_provider="unorouter",
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=503, detail="No configured free model provider is available for learning analysis.") from exc
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        raise HTTPException(status_code=502, detail=f"Learning analysis failed safely: {type(exc).__name__}") from exc
    try:
        suggestion = json.loads(model_result.text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Learning model did not return valid JSON.") from exc
    expected_keys = {"role_key", "note", "rationale", "expected_measurement", "risk_level"}
    if not isinstance(suggestion, dict) or set(suggestion) != expected_keys:
        raise HTTPException(status_code=422, detail="Learning model returned an invalid proposal shape.")
    role_key = suggestion["role_key"]
    if role_key not in supported_roles:
        raise HTTPException(status_code=422, detail="Learning model selected a role not supported by the evidence.")
    try:
        default_workforce().get(role_key)
        proposal = ImprovementProposal(
            id=uuid4(), target=role_key, change_summary=suggestion["note"],
            rationale=suggestion["rationale"],
            expected_measurement=suggestion["expected_measurement"],
            risk_level=suggestion["risk_level"],
            based_on_evaluations=tuple(payload.evaluation_ids),
            state=ProposalState.PROPOSED,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Learning proposal failed validation: {exc}") from exc
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="agent", actor_id="learning-reviewer",
        action="learning.ai_proposal_created", subject_type="improvement_proposal",
        subject_id=str(proposal.id), outcome="proposed", correlation_id=str(uuid4()),
        details={"role_key": role_key, "business_id": business_id,
                 "provider": model_result.provider, "model": model_result.model},
    )
    try:
        runtime.learning.save_proposal(proposal, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": str(proposal.id), "target": proposal.target,
        "business_id": business_id,
        "change_summary": proposal.change_summary, "rationale": proposal.rationale,
        "expected_measurement": proposal.expected_measurement, "risk_level": proposal.risk_level,
        "state": proposal.state.value, "provider": model_result.provider,
        "model": model_result.model, "owner_approval_required": True,
        "note_applied": False,
    }


@app.post("/learning/proposals/{proposal_id}/apply-note", dependencies=[Depends(require_owner_key)])
def apply_approved_learning_proposal(
    proposal_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    proposal = next(
        (item for item in runtime.learning.list_proposals() if item["id"] == str(proposal_id)),
        None,
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Learning proposal not found.")
    if proposal["state"] != ProposalState.APPROVED.value:
        raise HTTPException(status_code=409, detail="Only owner-approved learning proposals can be applied.")
    try:
        default_workforce().get(proposal["target"])
    except LookupError as exc:
        raise HTTPException(status_code=409, detail="Proposal target is not a known workforce role.") from exc
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.approved_note_applied", subject_type="agent_role",
        subject_id=proposal["target"], outcome="applied", correlation_id=str(uuid4()),
        details={"proposal_id": str(proposal_id), "evidence_ids": proposal["based_on_evaluations"],
                 "business_id": proposal["business_id"]},
    )
    try:
        note_id = runtime.learning.apply_proposal_as_note(proposal_id, owner_id="owner", record=event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"proposal_id": str(proposal_id), "note_id": note_id, "role_key": proposal["target"], "state": "implemented"}


@app.get("/learning/proposals", dependencies=[Depends(require_owner_key)])
def list_learning_proposals(
    business_id: str | None = None,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    proposals = runtime.learning.list_proposals(business_id=business_id)
    return {"count": len(proposals), "business_id": business_id or "all", "proposals": proposals}


@app.post("/learning/proposals/{proposal_id}/decision", dependencies=[Depends(require_owner_key)])
def decide_learning_proposal(
    proposal_id: UUID,
    payload: LearningDecisionInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.improvement_decision", subject_type="improvement_proposal",
        subject_id=str(proposal_id), outcome="approved" if payload.approved else "rejected",
        correlation_id=str(uuid4()), details={"rationale": payload.rationale},
    )
    changed = runtime.learning.decide_proposal(
        proposal_id, approved=payload.approved, owner_id="owner",
        rationale=payload.rationale, record=event,
    )
    if not changed:
        raise HTTPException(status_code=409, detail="Proposal not found or already decided.")
    return {"id": str(proposal_id), "state": "approved" if payload.approved else "rejected"}


@app.post("/learning/notes", dependencies=[Depends(require_owner_key)])
def create_approved_learning_note(
    payload: LearningNoteInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        default_workforce().get(payload.role_key)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="Unknown role key.") from exc
    if payload.business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.role_note_approved", subject_type="agent_role",
        subject_id=payload.role_key, outcome="approved", correlation_id=str(uuid4()),
        details={"evidence_refs": payload.evidence_refs, "business_id": payload.business_id},
    )
    try:
        note_id = runtime.learning.save_learning_note(
            role_key=payload.role_key, note=payload.note,
            evidence_refs=tuple(payload.evidence_refs), owner_id="owner", record=event,
            business_id=payload.business_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": note_id, "role_key": payload.role_key, "business_id": payload.business_id, "state": "approved"}


@app.get("/learning/notes/{role_key}", dependencies=[Depends(require_owner_key)])
def list_approved_learning_notes(
    role_key: str,
    business_id: str = "core",
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        default_workforce().get(role_key)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="Unknown role key.") from exc
    if business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    notes = runtime.learning.list_learning_notes(role_key, business_id=business_id)
    return {"role_key": role_key, "business_id": business_id, "count": len(notes), "notes": notes}


@app.post("/work-items/{item_id}/handoffs", dependencies=[Depends(require_owner_key)])
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


@app.get("/work-items/{item_id}/handoffs", dependencies=[Depends(require_owner_key)])
def list_agent_handoffs(
    item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    handoffs = runtime.handoffs.list_for_work_item(item_id)
    return {"count": len(handoffs), "handoffs": [_handoff_payload(item) for item in handoffs]}


@app.post("/handoffs/{handoff_id}/accept", dependencies=[Depends(require_owner_key)])
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


@app.post("/handoffs/{handoff_id}/decline", dependencies=[Depends(require_owner_key)])
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


@app.post("/handoffs/{handoff_id}/deliver", dependencies=[Depends(require_owner_key)])
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


@app.post("/executive/plan", dependencies=[Depends(require_owner_key)])
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


@app.post("/work-items/{item_id}/manager-proposal", dependencies=[Depends(require_owner_key)])
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
            detail="The department manager must be ACTIVE with the expected role, department, and management team.",
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
                profile is None or profile.state != AgentState.ACTIVE
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
    if item.state != TaskState.DRAFT or item.assigned_agent_id is not None:
        raise HTTPException(status_code=409, detail="Delegation planning is allowed only for unassigned draft work items.")
    try:
        plan = plan_department_work(item, payload.required_capabilities, max_specialists=payload.max_specialists)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profiles = store.list_agents(limit=1000)
    manager = next((agent for agent in profiles if agent.role_key == plan.manager_role_key and agent.department == item.department), None)
    if (
        manager is None or manager.state != AgentState.ACTIVE
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
                profile is None or profile.state != AgentState.ACTIVE
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


@app.post("/work-items/{item_id}/delegation-proposals/{proposal_id}/approve", dependencies=[Depends(require_owner_key)])
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


@app.get("/work-items/{item_id}/workflow", dependencies=[Depends(require_owner_key)])
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


@app.post("/work-items/{item_id}/review", dependencies=[Depends(require_owner_key)])
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


@app.get("/work-items/{item_id}/deliverables", dependencies=[Depends(require_owner_key)])
def list_work_item_deliverables(
    item_id: UUID, store: SQLiteStore = Depends(get_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    artifacts = store.list_deliverables(item_id)
    return {"count": len(artifacts), "deliverables": artifacts}


@app.get("/usage/model", dependencies=[Depends(require_owner_key)])
def model_usage_summary(
    business_id: str | None = None,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-only, durable inference usage and cost accounting, optionally scoped by business."""
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    return runtime.usage.summary(limit=100, business_id=business_id)


@app.get("/audit/verify", dependencies=[Depends(require_owner_key)])
def verify_audit(store: SQLiteStore = Depends(get_store)) -> dict:
    return {
        "event_count": store.audit_event_count(),
        "chain_valid": store.verify_audit_chain(),
    }


@app.post("/commercial/suppliers", dependencies=[Depends(require_owner_key)])
def create_commercial_supplier(payload: CommercialSupplierInput, store: SQLiteStore = Depends(get_store)) -> dict:
    if payload.business_id not in {"physical-agency", "physical-brand"}:
        raise HTTPException(status_code=422, detail="Supplier records belong only to the physical-products agency or own-brand business.")
    relationship_type = "agency_supplier" if payload.business_id == "physical-agency" else "own_brand_supplier"
    now = datetime.now(timezone.utc)
    supplier_id = str(uuid4())
    record = {
        "id": supplier_id, "business_id": payload.business_id, "relationship_type": relationship_type,
        "name": payload.name.strip(), "contact_name": payload.contact_name, "email": payload.email,
        "phone": payload.phone, "country": payload.country,
        "product_categories": [value.strip() for value in payload.product_categories if value.strip()],
        "notes": payload.notes, "created_at": now.isoformat(), "updated_at": now.isoformat(),
    }
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="commercial.supplier_created", subject_type="commercial_supplier",
        subject_id=supplier_id, outcome="draft_saved", correlation_id=str(uuid4()),
        details={"business_id": payload.business_id, "relationship_type": relationship_type, "external_contact_made": False},
    )
    try:
        store.create_commercial_supplier(record, event)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"supplier_id": supplier_id, "business_id": payload.business_id,
            "relationship_type": relationship_type, "verification_status": "draft", "external_contact_made": False}


@app.get("/commercial/suppliers", dependencies=[Depends(require_owner_key)])
def list_commercial_suppliers(business_id: str | None = None, store: SQLiteStore = Depends(get_store)) -> dict:
    if business_id is not None and business_id not in {"physical-agency", "physical-brand"}:
        raise HTTPException(status_code=422, detail="Supplier records are available only for physical business units.")
    suppliers = store.list_commercial_suppliers(business_id=business_id)
    return {"count": len(suppliers), "suppliers": list(suppliers)}


@app.post("/commercial/suppliers/{supplier_id}/status", dependencies=[Depends(require_owner_key)])
def update_commercial_supplier_status(
    supplier_id: UUID, payload: CommercialSupplierStatusInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    if payload.confirm_owner_decision is not True:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to change supplier verification status.")
    if payload.status not in {"verified", "blocked"}:
        raise HTTPException(status_code=422, detail="Supplier status must be verified or blocked.")
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="commercial.supplier_status_changed", subject_type="commercial_supplier",
        subject_id=str(supplier_id), outcome=payload.status, correlation_id=str(uuid4()),
        details={"verification_status": payload.status, "external_contact_made": False},
    )
    if not store.update_commercial_supplier_status(str(supplier_id), payload.status, event):
        raise HTTPException(status_code=404, detail="Supplier not found or already blocked.")
    return {"supplier_id": str(supplier_id), "status": payload.status,
            "external_contact_made": False, "purchase_or_commitment_created": False}


# Company-wide venture portfolio. This is intentionally distinct from operating
# business units: discovering an opportunity never creates a business or
# authorizes spending, publishing, customer contact, or a launch.
def _venture_portfolio(runtime: OpenCompanyRuntime) -> VenturePortfolio:
    return VenturePortfolio(runtime.store._connection, runtime.store._lock)


@app.get("/venture-opportunities", dependencies=[Depends(require_owner_key)])
def list_venture_opportunities(
    status: str | None = None,
    limit: int = 100,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        items = _venture_portfolio(runtime).list(status=status, limit=limit)
        return {"items": list(items), "count": len(items)}
    except VenturePortfolioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/venture-opportunities", dependencies=[Depends(require_owner_key)])
def create_venture_opportunity(
    payload: VentureOpportunityInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        item = _venture_portfolio(runtime).create(
            title=payload.title, slug=payload.slug, business_model=payload.business_model,
            description=payload.description, target_market=payload.target_market,
            evidence=payload.evidence,
        )
        return {"item": item, "message": "Opportunity saved in the company-wide portfolio; no business unit was created."}
    except VenturePortfolioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/venture-opportunities/{opportunity_id}/status", dependencies=[Depends(require_owner_key)])
def transition_venture_opportunity(
    opportunity_id: str,
    payload: VentureOpportunityStatusInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        item = _venture_portfolio(runtime).transition(
            opportunity_id, status=payload.status, rationale=payload.rationale,
            confirm_owner_approval=payload.confirm_owner_approval,
        )
    except VenturePortfolioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    return {"item": item, "message": "Status recorded. Launch approval does not provision accounts, spend money, or publish anything."}


@app.get("/venture-opportunities/{opportunity_id}/events", dependencies=[Depends(require_owner_key)])
def list_venture_opportunity_events(
    opportunity_id: str,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    portfolio = _venture_portfolio(runtime)
    if portfolio.get(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    return {"items": list(portfolio.events(opportunity_id))}
