"""Standalone OpenCompany API, independent of legacy AIOS modules.

The service exposes a public read-only health check. Company records and
write operations require owner authentication. Model calls are cost-gated to explicitly configured free providers; external business actions remain outside the runtime's authority.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import tempfile
import time
from threading import Lock
from datetime import datetime, timezone
from dataclasses import replace
from functools import lru_cache
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from opencompany_core.domain import AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.lifecycle import StateTransitionError, transition_work_item
from opencompany_core.persistence import SQLiteStore
from opencompany_core.planning import PlanError, WorkPlan, action_requires_owner_approval
from opencompany_core.workforce import default_workforce
from opencompany_core.organization import default_organization
from opencompany_core.media_studio import video_capabilities
from opencompany_core.provider_catalog import free_provider_candidates
from opencompany_core.unorouter_adapter import (
    UNOROUTER_AUTO_FREE_MODEL, discover_free_models, unorouter_configuration_status,
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
from opencompany_core.github_evolution import GitHubEvolutionError
from opencompany_core.code_evolution import CodeEvolutionError, generate_code_evolution_pr
from opencompany_core.api_anything import ApiAnythingError
from opencompany_app.runtime import OpenCompanyRuntime, create_runtime
from opencompany_app.dashboard import OWNER_DASHBOARD_HTML


app = FastAPI(
    title="OpenCompany Core",
    version="0.2.0",
    description="Owner-authenticated API for OpenCompany's independently authored operating core.",
)

# Per-process login throttling. The API key is a bootstrap credential; this
# protects the session exchange endpoint from unlimited online guessing.
_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_LOCK = Lock()
_LOGIN_WINDOW_SECONDS = 900
_LOGIN_MAX_FAILURES = 5
_LOGIN_MAX_TRACKED_CLIENTS = 10_000

# In-memory, owner-authenticated async provider-test jobs. The inference request
# may outlive browser/proxy request timeouts; clients poll the job instead.
_UNOROUTER_TESTS: dict[str, dict] = {}
_UNOROUTER_TESTS_LOCK = Lock()
_UNOROUTER_TESTS_MAX = 50


def _login_retry_after(client_key: str, *, failed: bool = False) -> int:
    now = time.monotonic()
    with _LOGIN_LOCK:
        for key, attempts in list(_LOGIN_FAILURES.items()):
            fresh = [stamp for stamp in attempts if now - stamp < _LOGIN_WINDOW_SECONDS]
            if fresh:
                _LOGIN_FAILURES[key] = fresh
            else:
                _LOGIN_FAILURES.pop(key, None)
        if client_key not in _LOGIN_FAILURES and len(_LOGIN_FAILURES) >= _LOGIN_MAX_TRACKED_CLIENTS:
            oldest_key = min(
                _LOGIN_FAILURES,
                key=lambda key: _LOGIN_FAILURES[key][-1] if _LOGIN_FAILURES[key] else now,
            )
            _LOGIN_FAILURES.pop(oldest_key, None)
        attempts = _LOGIN_FAILURES.setdefault(client_key, [])
        if failed:
            attempts.append(now)
        if len(attempts) < _LOGIN_MAX_FAILURES:
            return 0
        return max(1, int(_LOGIN_WINDOW_SECONDS - (now - attempts[0])))


def _clear_login_failures(client_key: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.pop(client_key, None)


class OwnerLoginInput(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


class UnoRouterSettingsInput(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    model: str = Field(min_length=3, max_length=200, pattern=r"^[A-Za-z0-9._/-]+:free$")
    confirm_free: bool

class UnoRouterDiscoveryInput(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


class GitHubEvolutionSettingsInput(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    confirm_draft_pr_only: bool



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
    max_specialists: int = Field(default=15, ge=1, le=50)


class ApiAnythingCallInput(BaseModel):
    site: str = Field(min_length=1, max_length=80)
    operation: str = Field(min_length=1, max_length=100)
    args: dict = Field(default_factory=dict)
    max_age_ms: int = Field(default=0, ge=0, le=86400000)


class ApiAnythingBatchInput(BaseModel):
    calls: list[dict] = Field(min_length=1, max_length=20)


class CodeEvolutionInput(BaseModel):
    problem: str = Field(min_length=1, max_length=3000)
    file_paths: list[str] = Field(min_length=1, max_length=3)


class OutcomeEvaluationInput(BaseModel):
    grade: OutcomeGrade
    rubric_scores: dict[str, int] = Field(min_length=1, max_length=20)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)
    observations: str = Field(min_length=1, max_length=6000)


class LearningAIProposalInput(BaseModel):
    evaluation_ids: list[UUID] = Field(min_length=1, max_length=5)


class ImprovementProposalInput(BaseModel):
    target: str = Field(min_length=1, max_length=2000)
    change_summary: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)
    expected_measurement: str = Field(min_length=1, max_length=2000)
    risk_level: str = Field(min_length=1, max_length=80)
    based_on_evaluations: list[UUID] = Field(min_length=1, max_length=20)


class LearningDecisionInput(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)


class LearningNoteInput(BaseModel):
    role_key: str = Field(min_length=1, max_length=160)
    note: str = Field(min_length=1, max_length=3000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)


class HandoffCreateInput(BaseModel):
    recipient_agent_id: UUID
    purpose: str = Field(min_length=1, max_length=240)
    requested_result: str = Field(min_length=1, max_length=1200)
    context: str = Field(min_length=1, max_length=6000)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=20)


class HandoffDeliverInput(BaseModel):
    response_artifact_ids: list[UUID] = Field(min_length=1, max_length=20)


class ExecutivePlanInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=12000)
    max_tasks: int = Field(default=8, ge=1, le=10)


class ManagerProposalInput(BaseModel):
    max_specialists: int = Field(default=15, ge=1, le=50)


class WorkItemTransitionInput(BaseModel):
    target_state: TaskState


class WorkItemReviewInput(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)


@lru_cache(maxsize=1)
def _default_runtime() -> OpenCompanyRuntime:
    return create_runtime()


@app.on_event("startup")
def initialize_autonomous_runtime() -> None:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        return
    bootstrap_enabled = os.environ.get("OPENCOMPANY_BOOTSTRAP_WORKFORCE", "false").casefold() == "true"
    activate_enabled = os.environ.get("OPENCOMPANY_AUTO_ACTIVATE_WORKFORCE", "false").casefold() == "true"
    if not (bootstrap_enabled or activate_enabled):
        return
    runtime = _default_runtime()
    if bootstrap_enabled:
        bootstrap_department_managers(runtime.store)
        bootstrap_specialist_profiles(runtime.store)
        bootstrap_executive_orchestrator(runtime.store)
    if activate_enabled:
        runtime.store.activate_all_draft_agents_with_audit()
    # Never start inference at process boot from saved credentials alone.
    # The owner must run the live zero-cost provider test in this process;
    # that verified action is the only path to start_workers_if_ready().


@app.on_event("shutdown")
def close_autonomous_runtime() -> None:
    if _default_runtime.cache_info().currsize:
        _default_runtime().close()
        _default_runtime.cache_clear()


def get_runtime() -> OpenCompanyRuntime:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_runtime()


def get_optional_runtime() -> OpenCompanyRuntime | None:
    # Provider readiness is intentionally public and credential-free. Only
    # load owner-persisted settings when the owner runtime is configured.
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        return None
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
            # Browser sessions are same-origin only. SameSite cookies and a
            # session-bound CSRF token are required, and Origin must match Host.
            # API-key clients remain available for explicit server-to-server use.
            if mutating:
                origin = request.headers.get("origin")
                host = request.headers.get("host", "").casefold()
                try:
                    origin_parts = urlsplit(origin or "")
                    origin_host = origin_parts.netloc.casefold()
                    valid_origin = (
                        origin_parts.scheme in {"http", "https"}
                        and bool(origin_host)
                        and origin_host == host
                        and origin_parts.path in {"", "/"}
                        and not origin_parts.query
                        and not origin_parts.fragment
                    )
                except ValueError:
                    valid_origin = False
                if not valid_origin:
                    raise HTTPException(status_code=403, detail="Owner session requests must use the same origin.")
            return "owner"
    client_key = request.client.host if request.client else "unknown"
    if x_opencompany_api_key and hmac.compare_digest(x_opencompany_api_key, expected):
        _clear_login_failures(client_key)
        return "owner"
    if x_opencompany_api_key:
        retry_after = _login_retry_after(client_key, failed=True)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Too many failed owner authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    raise HTTPException(status_code=401, detail="Owner authentication failed.")


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
        details={"state": item.state.value, "department": item.department},
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


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: the ASGI process is responsive."""
    return {"status": "ok", "service": "opencompany-core", "mode": "owner-authenticated"}


@app.get("/ready")
def readiness(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Readiness probe: owner configuration and persistent storage are usable.

    Provider readiness is intentionally not required here: the owner dashboard
    must be reachable before the owner can configure the free provider.
    """
    try:
        with runtime.store._lock:
            connection = runtime.store._connection
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or str(result[0]).casefold() != "ok":
                raise RuntimeError("database integrity check failed")
            connection.execute("SELECT 1").fetchone()
            # A readable database is not necessarily writable (for example,
            # when a persistent volume is mounted with the wrong owner).
            # Acquire and release a write transaction so readiness catches
            # that deployment failure before owner login attempts to create
            # a session or other state.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ROLLBACK")
        fleet = runtime.fleet.status()
    except Exception as exc:
        # Keep internal database and filesystem diagnostics out of public probes.
        raise HTTPException(status_code=503, detail="OpenCompany storage is not ready.") from exc
    return {
        "status": "ready",
        "service": "opencompany-core",
        "storage": "ok",
        "worker_fleet_running": fleet.running,
        "provider_required_for_readiness": False,
    }


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
                "playbook": {
                    "intake_requirements": list(role.playbook.intake_requirements),
                    "workflow_steps": list(role.playbook.workflow_steps),
                    "deliverable_contract": list(role.playbook.deliverable_contract),
                    "quality_rubric": list(role.playbook.quality_rubric),
                    "escalation_triggers": list(role.playbook.escalation_triggers),
                    "tool_scopes": list(role.playbook.tool_scopes),
                },
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




@app.post("/settings/providers/unorouter/discover", dependencies=[Depends(require_owner_key)])
def discover_unorouter_models(payload: UnoRouterDiscoveryInput) -> dict:
    try:
        models = discover_free_models(payload.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"UnoRouter model discovery failed safely: {exc}") from exc
    return {"success": True, "models": models, "count": len(models),
            "source": "authenticated-key-list intersected with live zero-price catalogue",
            "paid_models_included": False}


@app.get("/settings/providers/unorouter", dependencies=[Depends(require_owner_key)])
def get_unorouter_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    status = runtime.secret_vault.status("unorouter")
    configuration_error = None
    try:
        saved = runtime.secret_vault.get("unorouter")
    except SecretVaultError:
        saved = None
        configuration_error = "Stored UnoRouter credentials cannot be decrypted. Check the stable server encryption key, or replace/remove the saved credentials."
    return {
        "configured": saved is not None, "model": saved["model"] if saved else None,
        "api_key_present": status["configured"], "credentials_decryptable": saved is not None,
        "configuration_error": configuration_error or runtime.secret_vault_errors.get("unorouter"),
        "real_inference_verified": runtime.unorouter_tested_at is not None,
        "last_tested_at": runtime.unorouter_tested_at, "automatic_paid_fallback": False,
        **status,
    }


@app.get("/settings/providers/unorouter/models", dependencies=[Depends(require_owner_key)])
def list_unorouter_free_models(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Discover all free models accessible to the already-saved inference key."""
    try:
        saved = runtime.secret_vault.get("unorouter")
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored UnoRouter credentials cannot be decrypted.") from exc
    if not saved:
        raise HTTPException(status_code=409, detail="Save the UnoRouter API key first.")
    try:
        models = discover_free_models(saved["api_key"], force_refresh=True)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"UnoRouter catalogue refresh failed safely: {exc}") from exc
    return {
        "provider": "unorouter", "count": len(models), "models": list(models),
        "routing_mode": "automatic_all_free_models",
        "catalogue_cache_seconds": 300, "paid_models_included": False,
        "paid_fallback": False,
    }


@app.put("/settings/providers/unorouter", dependencies=[Depends(require_owner_key)])
def save_unorouter_settings(payload: UnoRouterSettingsInput, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if payload.confirm_free is not True:
        raise HTTPException(status_code=422, detail="Owner must explicitly confirm the selected model is free.")
    if payload.model != UNOROUTER_AUTO_FREE_MODEL and not payload.model.endswith(":free"):
        raise HTTPException(status_code=422, detail="Only explicitly free model IDs or automatic free-catalog routing are accepted.")
    if payload.model != UNOROUTER_AUTO_FREE_MODEL:
        try:
            discovered = discover_free_models(payload.api_key)
        except ProviderUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"UnoRouter could not revalidate the selected free model: {exc}") from exc
        if payload.model not in discovered:
            raise HTTPException(status_code=409, detail="The selected model is not currently listed as free, online, and available to this API key. Load the free-model list again.")
    try:
        runtime.stop_workers_for_provider_change()
        revision = runtime.secret_vault.put("unorouter", {"api_key": payload.api_key, "model": payload.model})
        runtime.configure_unorouter(
            {"api_key": payload.api_key, "model": payload.model, "confirmed_free": "true"},
            workers_already_stopped=True,
        )
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Workers are still processing; provider settings were not changed.") from exc
    return {"configured": True, "model": payload.model, "api_key_saved": True, "revision": revision,
            "billing_mode": "free_confirmed", "automatic_paid_fallback": False, "live_inference_tested": False}


def _worker_autostart_enabled() -> bool:
    return os.environ.get("OPENCOMPANY_WORKER_AUTOSTART", "false").strip().casefold() in {"1", "true", "yes", "on"}


def _run_unorouter_test(runtime: OpenCompanyRuntime, job_id: str) -> None:
    with _UNOROUTER_TESTS_LOCK:
        job = _UNOROUTER_TESTS.get(job_id)
        if job is None:
            return
        job["status"] = "running"
    try:
        result = runtime.gateway.complete(
            ModelRequest(prompt="Reply with exactly: OPENCOMPANY_UNOROUTER_OK",
                         request_id=f"owner-unorouter-test-{uuid4()}", max_output_tokens=24),
            request_budget_usd=0.0, preferred_provider="unorouter",
        )
        if result.text.strip() != "OPENCOMPANY_UNOROUTER_OK":
            raise ProviderUnavailable("UnoRouter returned an unexpected test response.")
        runtime.unorouter_tested_at = datetime.now(timezone.utc).isoformat()
        worker_started = False
        worker_start_error = None
        try:
            worker_started = runtime.start_workers_if_ready()
        except Exception as exc:
            worker_start_error = type(exc).__name__
        outcome = {
            "status": "succeeded", "success": True, "provider": result.provider,
            "model": result.model, "cost_usd": result.cost_usd,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            "output_preview": result.text[:160], "tested_at": runtime.unorouter_tested_at,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": worker_started, "worker_start_error": worker_start_error,
            "paid_fallback": False,
        }
    except NoEligibleProvider:
        outcome = {
            "status": "failed", "success": False,
            "error": "No confirmed-free UnoRouter model is configured and available.",
            "provider": "unorouter", "model": None, "cost_usd": 0.0,
            "input_tokens": 0, "output_tokens": 0, "output_preview": None,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": False, "worker_start_error": None, "paid_fallback": False,
        }
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        # Adapter diagnostics are deliberately bounded and contain no credentials.
        reason = " ".join(str(exc).split())[:600] or type(exc).__name__
        outcome = {
            "status": "failed", "success": False,
            "error": f"UnoRouter test failed safely: {reason}. No paid fallback was attempted.",
            "provider": "unorouter", "model": None, "cost_usd": 0.0,
            "input_tokens": 0, "output_tokens": 0, "output_preview": None,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": False, "worker_start_error": None, "paid_fallback": False,
        }
    except Exception as exc:
        outcome = {
            "status": "failed", "success": False,
            "error": f"UnoRouter test failed safely ({type(exc).__name__}). No paid fallback was attempted.",
            "provider": "unorouter", "model": None, "cost_usd": 0.0,
            "input_tokens": 0, "output_tokens": 0, "output_preview": None,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": False, "worker_start_error": None, "paid_fallback": False,
        }
    with _UNOROUTER_TESTS_LOCK:
        if job_id in _UNOROUTER_TESTS:
            _UNOROUTER_TESTS[job_id].update(outcome)


@app.post("/settings/providers/unorouter/test", dependencies=[Depends(require_owner_key)])
def test_unorouter_connection(
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> JSONResponse:
    # A browser/proxy can close a long-running inference request. Start the
    # bounded zero-dollar test in a background task and let the owner poll it.
    with _UNOROUTER_TESTS_LOCK:
        active = next((
            job for job in reversed(list(_UNOROUTER_TESTS.values()))
            if job.get("status") in {"queued", "running"}
        ), None)
        if active is not None:
            return JSONResponse(status_code=202, content={
                "job_id": active["job_id"], "status": active["status"],
            })
        job_id = str(uuid4())
        _UNOROUTER_TESTS[job_id] = {"job_id": job_id, "status": "queued"}
        while len(_UNOROUTER_TESTS) > _UNOROUTER_TESTS_MAX:
            oldest = next(iter(_UNOROUTER_TESTS))
            if _UNOROUTER_TESTS[oldest].get("status") in {"queued", "running"}:
                break
            _UNOROUTER_TESTS.pop(oldest, None)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "queued"},
        background=BackgroundTask(_run_unorouter_test, runtime, job_id),
    )


@app.get("/settings/providers/unorouter/test/{job_id}", dependencies=[Depends(require_owner_key)])
def get_unorouter_test_status(job_id: UUID) -> dict:
    with _UNOROUTER_TESTS_LOCK:
        job = _UNOROUTER_TESTS.get(str(job_id))
        if job is None:
            raise HTTPException(status_code=404, detail="UnoRouter test job was not found or has expired.")
        return dict(job)


@app.delete("/settings/providers/unorouter", dependencies=[Depends(require_owner_key)])
def remove_unorouter_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    try:
        runtime.stop_workers_for_provider_change()
        removed = runtime.secret_vault.delete("unorouter")
        runtime.configure_unorouter(None, workers_already_stopped=True)
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored provider settings could not be removed safely.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Workers are still processing; provider settings were not changed.") from exc
    return {"removed": removed, "configured": False, "paid_fallback": False}


@app.get("/settings/integrations/github-evolution", dependencies=[Depends(require_owner_key)])
def get_github_evolution_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    return {
        "configured": runtime.github_evolution is not None,
        "repository": runtime.github_evolution.repository if runtime.github_evolution else os.environ.get("OPENCOMPANY_GITHUB_REPOSITORY"),
        "base_branch": runtime.github_evolution.base_branch if runtime.github_evolution else os.environ.get("OPENCOMPANY_GITHUB_BASE_BRANCH", "clean-room-rebuild"),
        "token_present": runtime.secret_vault.status("github_evolution")["configured"],
        "configuration_error": runtime.secret_vault_errors.get("github_evolution"),
        "access_verified": runtime.github_evolution_tested_at is not None,
        "verified_at": runtime.github_evolution_tested_at,
        "token": None,
        "auto_merge": False,
        "auto_deploy": False,
        "allowed_output": "draft_pull_requests_only",
    }


@app.put("/settings/integrations/github-evolution", dependencies=[Depends(require_owner_key)])
def save_github_evolution_settings(
    payload: GitHubEvolutionSettingsInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if payload.confirm_draft_pr_only is not True:
        raise HTTPException(status_code=422, detail="Owner must confirm GitHub access is for draft PR creation only.")
    if not os.environ.get("OPENCOMPANY_GITHUB_REPOSITORY", "").strip():
        raise HTTPException(status_code=503, detail="The GitHub repository must be configured by the service owner before saving a token.")
    try:
        runtime.secret_vault.put("github_evolution", {"token": payload.token})
        runtime.configure_github_evolution(payload.token)
    except (SecretVaultError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="GitHub credentials could not be saved safely.") from exc
    return {
        "configured": True,
        "repository": runtime.github_evolution.repository,
        "base_branch": runtime.github_evolution.base_branch,
        "token_saved": True,
        "token_echoed": False,
        "auto_merge": False,
        "auto_deploy": False,
    }


@app.post("/settings/integrations/github-evolution/test", dependencies=[Depends(require_owner_key)])
def test_github_evolution_access(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.github_evolution is None:
        raise HTTPException(status_code=503, detail="GitHub code evolution is not configured.")
    try:
        result = runtime.github_evolution.verify_access()
    except GitHubEvolutionError as exc:
        runtime.github_evolution_tested_at = None
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    runtime.github_evolution_tested_at = datetime.now(timezone.utc).isoformat()
    return {**result, "verified_at": runtime.github_evolution_tested_at}


@app.delete("/settings/integrations/github-evolution", dependencies=[Depends(require_owner_key)])
def remove_github_evolution_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    try:
        removed = runtime.secret_vault.delete("github_evolution")
        runtime.configure_github_evolution(None)
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="GitHub credentials could not be removed safely.") from exc
    return {"removed": removed, "configured": False, "token_echoed": False, "auto_merge": False, "auto_deploy": False}


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
                 "team_key": agent.team_key, "request_budget_usd": 0.0},
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
    status = runtime.fleet.status()
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "worker_process_autostarted": status.running,
        "execution_requires_explicit_worker_process": not status.running,
        "worker_autostart_configured": os.environ.get("OPENCOMPANY_WORKER_AUTOSTART", "false").casefold() == "true",
        "free_provider_ready": bool(runtime.gateway.eligible_providers(request_budget_usd=0.0)),
    }


@app.get("/workers/status", dependencies=[Depends(require_owner_key)])
def worker_fleet_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    status = runtime.fleet.status()
    return {
        "running": status.running,
        "concurrency": status.concurrency,
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
    if runtime.unorouter_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the owner-triggered zero-cost UnoRouter test in this process before starting workers.")
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(status_code=503, detail="No owner-configured free inference provider is available; worker start is blocked.")
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
    if runtime.unorouter_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the owner-triggered zero-cost UnoRouter test in this process before executing a worker cycle.")
    agent = runtime.store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    if agent.state != AgentState.ACTIVE or not agent.role_key:
        raise HTTPException(status_code=409, detail="Agent must be explicitly ACTIVE with a role.")
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(status_code=503, detail="No owner-configured free inference provider is available; worker execution is blocked.")
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

    
@app.get("/integrations/api-anything/status", dependencies=[Depends(require_owner_key)])
def api_anything_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        return {"enabled": False, "mode": "read-only", "max_tier": 1, "writes_enabled": False}
    try:
        health = runtime.api_anything.health()
        return {
            "enabled": True, "mode": "read-only", "max_tier": 1,
            "writes_enabled": False, "health": health,
        }
    except ApiAnythingError as exc:
        return {"enabled": True, "mode": "read-only", "writes_enabled": False, "healthy": False, "error": str(exc)}


@app.get("/integrations/api-anything/sites", dependencies=[Depends(require_owner_key)])
def api_anything_sites(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        return runtime.api_anything.list_sites()
    except ApiAnythingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/integrations/api-anything/find", dependencies=[Depends(require_owner_key)])
def api_anything_find(q: str, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        return runtime.api_anything.find_sites(q)
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/integrations/api-anything/sites/{site}/operations", dependencies=[Depends(require_owner_key)])
def api_anything_operations(site: str, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        return runtime.api_anything.list_operations(site)
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/integrations/api-anything/call", dependencies=[Depends(require_owner_key)])
def api_anything_read_call(
    payload: ApiAnythingCallInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        result = runtime.api_anything.call_read(
            payload.site, payload.operation, payload.args, max_age_ms=payload.max_age_ms
        )
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": "read-only", "max_tier": 1, "result": result}


@app.post("/integrations/api-anything/batch", dependencies=[Depends(require_owner_key)])
def api_anything_read_batch(
    payload: ApiAnythingBatchInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        result = runtime.api_anything.call_batch(payload.calls)
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": "read-only", "max_tier": 1, "result": result}


@app.get("/code-evolution/config-status", dependencies=[Depends(require_owner_key)])
def code_evolution_config_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    provider_verified = runtime.unorouter_tested_at is not None
    github_verified = runtime.github_evolution_tested_at is not None
    return {
        "configured": runtime.github_evolution is not None,
        "enabled": runtime.github_evolution is not None and github_verified and provider_verified,
        "access_verified": github_verified,
        "provider_verified": provider_verified,
        "verified_at": runtime.github_evolution_tested_at,
        "repository": runtime.github_evolution.repository if runtime.github_evolution else None,
        "base_branch": runtime.github_evolution.base_branch if runtime.github_evolution else None,
        "auto_merge": False,
        "auto_deploy": False,
    }


@app.post("/code-evolution/proposals", dependencies=[Depends(require_owner_key)])
def create_code_evolution_proposal(
    payload: CodeEvolutionInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    """Generate source edits and open a draft PR on an isolated feature branch."""
    if runtime.github_evolution is None:
        raise HTTPException(
            status_code=503,
            detail="Code evolution is not connected. Configure the repository on the service and save a GitHub token in the owner dashboard.",
        )
    if runtime.unorouter_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the owner-triggered zero-cost UnoRouter test before creating code-evolution proposals.")
    if runtime.github_evolution_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the read-only GitHub repository access test before creating code-evolution proposals.")
    try:
        result = generate_code_evolution_pr(
            payload.problem, tuple(payload.file_paths),
            runtime.gateway, runtime.github_evolution,
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=503, detail="No owner-configured free model provider is available for code evolution.") from exc
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        raise HTTPException(status_code=502, detail=f"Code model request failed safely: {type(exc).__name__}") from exc
    except (CodeEvolutionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubEvolutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    store.append_audit_record(AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="code_evolution.draft_pull_request_created",
        subject_type="github_pull_request", subject_id=str(result.pull_request.number),
        outcome="draft_pr_created", correlation_id=str(uuid4()),
        details={
            "url": result.pull_request.url, "branch": result.pull_request.branch,
            "commit_sha": result.pull_request.commit_sha,
            "changed_paths": list(result.changed_paths),
            "provider": result.provider, "model": result.model,
        },
    ))
    return {
        "pull_request_number": result.pull_request.number,
        "url": result.pull_request.url,
        "branch": result.pull_request.branch,
        "commit_sha": result.pull_request.commit_sha,
        "changed_paths": list(result.changed_paths),
        "provider": result.provider,
        "model": result.model,
        "draft": True,
        "merged": False,
        "deployed": False,
        "owner_merge_review_required": True,
    }


@app.get("/code-evolution/pull-requests/{number}", dependencies=[Depends(require_owner_key)])
def get_code_evolution_status(
    number: int,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if runtime.github_evolution is None:
        raise HTTPException(status_code=503, detail="GitHub code evolution is not configured.")
    try:
        status = runtime.github_evolution.get_pull_request(number)
    except (ValueError, GitHubEvolutionError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return status


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
    if not supported_roles:
        raise HTTPException(status_code=409, detail="Selected evaluations must cite deliverables with identifiable role keys.")
    prompt = (
        "OPENCOMPANY EVIDENCE-BASED LEARNING REVIEW\n"
        "Recommend one narrowly scoped role-learning note based only on the supplied owner evaluations and artifacts. "
        "Do not claim a permanent code change. Return only JSON with exactly these keys: role_key, note, rationale, "
        "expected_measurement, risk_level. The role_key must be one of the supplied roles. The note should be a concise "
        "operating improvement that can be inserted into that role's future prompt only after owner approval.\n"
        f"Supported role keys: {json.dumps(sorted(supported_roles))}\n"
        f"Evidence: {json.dumps(evidence_context, ensure_ascii=False)}"
    )
    try:
        model_result = runtime.gateway.complete(
            ModelRequest(prompt=prompt, request_id=str(uuid4()), max_output_tokens=1800),
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
        details={"role_key": role_key, "provider": model_result.provider, "model": model_result.model},
    )
    try:
        runtime.learning.save_proposal(proposal, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": str(proposal.id), "target": proposal.target,
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
        details={"proposal_id": str(proposal_id), "evidence_ids": proposal["based_on_evaluations"]},
    )
    try:
        note_id = runtime.learning.apply_proposal_as_note(proposal_id, owner_id="owner", record=event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"proposal_id": str(proposal_id), "note_id": note_id, "role_key": proposal["target"], "state": "implemented"}


@app.get("/learning/proposals", dependencies=[Depends(require_owner_key)])
def list_learning_proposals(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    proposals = runtime.learning.list_proposals()
    return {"count": len(proposals), "proposals": proposals}


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
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.role_note_approved", subject_type="agent_role",
        subject_id=payload.role_key, outcome="approved", correlation_id=str(uuid4()),
        details={"evidence_refs": payload.evidence_refs},
    )
    try:
        note_id = runtime.learning.save_learning_note(
            role_key=payload.role_key, note=payload.note,
            evidence_refs=tuple(payload.evidence_refs), owner_id="owner", record=event,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": note_id, "role_key": payload.role_key, "state": "approved"}


@app.get("/learning/notes/{role_key}", dependencies=[Depends(require_owner_key)])
def list_approved_learning_notes(
    role_key: str,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        default_workforce().get(role_key)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="Unknown role key.") from exc
    notes = runtime.learning.list_learning_notes(role_key)
    return {"role_key": role_key, "count": len(notes), "notes": notes}


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
        details={"work_item_id": str(item.id), "recipient_agent_id": str(payload.recipient_agent_id)},
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
) -> dict:
    handoff = runtime.handoffs.get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found.")
    now = datetime.now(timezone.utc)
    try:
        updated = accept_handoff(handoff, at=now)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="owner.accepted_agent_handoff", subject_type="agent_handoff",
        subject_id=str(handoff.id), outcome="accepted", correlation_id=str(uuid4()),
        details={"recipient_agent_id": str(handoff.recipient_agent_id)},
    )
    if not runtime.handoffs.transition(updated, HandoffState.PROPOSED, event):
        raise HTTPException(status_code=409, detail="Handoff changed; reload before retrying.")
    return {"handoff": _handoff_payload(updated), "execution_started": False}


@app.post("/handoffs/{handoff_id}/decline", dependencies=[Depends(require_owner_key)])
def decline_agent_handoff(
    handoff_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    handoff = runtime.handoffs.get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found.")
    now = datetime.now(timezone.utc)
    try:
        updated = decline_handoff(handoff, at=now)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="owner.declined_agent_handoff", subject_type="agent_handoff",
        subject_id=str(handoff.id), outcome="declined", correlation_id=str(uuid4()),
        details={"recipient_agent_id": str(handoff.recipient_agent_id)},
    )
    if not runtime.handoffs.transition(updated, HandoffState.PROPOSED, event):
        raise HTTPException(status_code=409, detail="Handoff changed; reload before retrying.")
    return {"handoff": _handoff_payload(updated)}


@app.post("/handoffs/{handoff_id}/deliver", dependencies=[Depends(require_owner_key)])
def deliver_agent_handoff(
    handoff_id: UUID,
    payload: HandoffDeliverInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    handoff = runtime.handoffs.get(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found.")
    now = datetime.now(timezone.utc)
    try:
        updated = deliver_handoff(handoff, response_artifact_ids=payload.response_artifact_ids, at=now)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="owner.recorded_handoff_delivery", subject_type="agent_handoff",
        subject_id=str(handoff.id), outcome="delivered", correlation_id=str(uuid4()),
        details={"response_artifact_ids": [str(value) for value in payload.response_artifact_ids]},
    )
    if not runtime.handoffs.transition(updated, HandoffState.ACCEPTED, event):
        raise HTTPException(status_code=409, detail="Handoff changed; reload before retrying.")
    return {"handoff": _handoff_payload(updated)}


@app.post("/executive/plan", dependencies=[Depends(require_owner_key)])
def create_executive_work_plan(
    payload: ExecutivePlanInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    """Ask the active CEO orchestrator to decompose an owner objective into draft tasks."""
    ceo = next(
        (agent for agent in store.list_agents(limit=1000)
         if agent.role_key == "chief_executive_orchestrator"),
        None,
    )
    if ceo is None or ceo.state != AgentState.ACTIVE:
        raise HTTPException(status_code=409, detail="The Chief Executive Orchestrator must be provisioned and explicitly ACTIVE.")
    try:
        plan = create_executive_plan(
            payload.title, payload.objective, runtime.gateway, max_tasks=payload.max_tasks
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=503, detail="No owner-configured free model provider is available for CEO planning.") from exc
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        raise HTTPException(status_code=502, detail=f"CEO model request failed safely: {type(exc).__name__}") from exc
    except ExecutivePlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    correlation_id = str(uuid4())
    now = datetime.now(timezone.utc)
    records = tuple(
        AuditRecord(
            id=uuid4(), occurred_at=now, actor_type="agent", actor_id=str(ceo.id),
            action="executive.draft_work_item_created", subject_type="work_item",
            subject_id=str(item.id), outcome="drafted", correlation_id=correlation_id,
            details={"provider": plan.provider, "model": plan.model, "plan_title": payload.title},
        )
        for item in plan.work_items
    )
    try:
        store.save_work_items_with_audit(plan.work_items, records)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Could not persist the complete executive plan: {type(exc).__name__}") from exc
    return {
        "plan_title": payload.title,
        "rationale": plan.rationale,
        "provider": plan.provider,
        "model": plan.model,
        "created_count": len(plan.work_items),
        "items": [
            {
                "id": str(item.id), "title": item.title, "objective": item.objective,
                "department": item.department, "state": item.state.value,
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
    manager_role = default_organization().get(item.department).manager_role_key
    manager = next(
        (agent for agent in store.list_agents(limit=1000)
         if agent.role_key == manager_role and agent.department == item.department),
        None,
    )
    if manager is None or manager.state != AgentState.ACTIVE:
        raise HTTPException(status_code=409, detail="The department manager profile must be provisioned and explicitly ACTIVE.")
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
            if profile is None:
                raise HTTPException(status_code=409, detail=f"Specialist profile is not provisioned: {specialist.role_key}")
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


@app.post("/work-items/{item_id}/review", dependencies=[Depends(require_owner_key)])
def review_work_item(
    item_id: UUID, payload: WorkItemReviewInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
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
            details={"evaluation_id": str(evaluation.id)},
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
def model_usage_summary(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Owner-only, durable inference usage and cost accounting."""
    return runtime.usage.summary(limit=100)


@app.get("/audit/verify", dependencies=[Depends(require_owner_key)])
def verify_audit(store: SQLiteStore = Depends(get_store)) -> dict:
    return {
        "event_count": store.audit_event_count(),
        "chain_valid": store.verify_audit_chain(),
    }
