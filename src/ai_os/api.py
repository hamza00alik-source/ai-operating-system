"""FastAPI application."""
from contextlib import asynccontextmanager
import logging
import threading
import unicodedata
import json
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import HTMLResponse
from ai_os.owner_dashboard import owner_dashboard

from ai_os.auth import (require_api_key, require_owner_key, create_owner_session, revoke_owner_session, SESSION_COOKIE, SESSION_TTL_DAYS)
from ai_os.config import get_settings
from ai_os.db import initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision, ApprovalOut, TaskCreate, TaskOut
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks
from ai_os.discovery import create_scan, list_scans, list_candidates, github_api_status, sync_free_api_catalog, list_free_api_catalog, run_pending_once as run_discovery_pending_once
from ai_os.schemas import DiscoveryScanCreate, CandidateReviewDecision
from ai_os.db import connect
from datetime import datetime, timezone
from ai_os.llm_gateway import list_providers, list_unorouter_catalog, generate, generate_with_fallback, test_provider, test_unorouter_personal
from ai_os.agent_runtime import create_run, get_run, list_runs, retry_run, recover_interrupted_runs, worker_pool, run_pending_once as run_agent_pending_once
from ai_os.credentials import save_openrouter, credential_status, CredentialVaultUnavailable, save_provider_credential, update_provider_model, provider_credential_statuses, save_business_integration, business_integration_statuses, delete_business_integration, get_business_integration_credential
from ai_os.brain import BUSINESS_IDS, brain_status, list_memories, review_memory, run_learning_cycle
from ai_os.business_registry import create_business, list_businesses, refresh_business_ids
from ai_os import venture_pipeline
from ai_os.workflows import list_templates, create_workflow, get_workflow, list_workflows, task_is_runnable
from ai_os.department_collaboration import send_message, list_messages, mark_message_read, delegate_task, list_delegations
from ai_os.executive_supervisor import executive_status, supervise_once, executive_supervisor_loop
from ai_os.inbox_supervisor import process_inbox_once
from ai_os.research_sources import capture_source, list_sources
from ai_os import website_api
from ai_os import platform_integrations, social_oauth, marketplace_integrations, code_evolution
from ai_os import business_ops
from pydantic import BaseModel, Field


class DepartmentMessageRequest(BaseModel):
    business_id: str = Field(default="core", min_length=1, max_length=64)
    sender_department: str = Field(min_length=1, max_length=64)
    recipient_department: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=12000)
    related_task_id: str | None = None


class DepartmentDelegationRequest(BaseModel):
    business_id: str = Field(default="core", min_length=1, max_length=64)
    from_department: str = Field(min_length=1, max_length=64)
    to_department: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=12000)
    parent_task_id: str | None = None



logger = logging.getLogger("ai_os.api")
_discovery_stop = threading.Event()
_discovery_thread: threading.Thread | None = None
_agent_stop = threading.Event()
_agent_thread: threading.Thread | None = None
_learning_thread: threading.Thread | None = None
_inbox_thread: threading.Thread | None = None
_executive_thread: threading.Thread | None = None


def _has_eligible_model() -> bool:
    try:
        return any(item.get("eligible") for item in list_providers())
    except Exception:
        logger.exception("Could not check free model-provider readiness.")
        return False


def _agent_worker_loop() -> None:
    """Run bounded queue consumers in the same single-replica API service."""
    poll_seconds = max(1, min(int(__import__("os").getenv("AI_OS_WORKER_POLL_SECONDS", "3")), 30))
    concurrency = max(1, min(int(__import__("os").getenv("AI_OS_WORKER_CONCURRENCY", "2")), 4))
    while not _agent_stop.is_set():
        if not _has_eligible_model():
            logger.warning("Agent queue is idle: no owner-confirmed eligible free model provider is configured.")
            _agent_stop.wait(30)
            continue
        try:
            recovered = recover_interrupted_runs()
            if recovered:
                logger.warning("Recovered %s interrupted run(s); they require owner retry.", recovered)
            worker_pool(_agent_stop, poll_seconds=poll_seconds, concurrency=concurrency)
        except Exception:
            logger.exception("Agent worker pool recovered from a process-level error.")
            _agent_stop.wait(5)


def _brain_learning_loop() -> None:
    """Run business-isolated deterministic learning cycles every six hours."""
    next_cycle = 0.0
    while not _agent_stop.is_set():
        try:
            if time.monotonic() >= next_cycle:
                for business_id in sorted(BUSINESS_IDS):
                    if _agent_stop.is_set():
                        break
                    try:
                        result = run_learning_cycle(business_id)
                        if not result.get("already_ran"):
                            logger.info("Autonomous brain cycle completed for %s: %s proposals",
                                        business_id, result.get("proposals_created", 0))
                    except Exception:
                        logger.exception("Autonomous brain cycle failed for %s", business_id)
                next_cycle = time.monotonic() + 21600
            _agent_stop.wait(30)
        except Exception:
            logger.exception("Brain learning scheduler recovered from an error.")
            _agent_stop.wait(30)


def _inbox_worker_loop() -> None:
    """Interpret internal department messages only when a free model is available."""
    while not _agent_stop.is_set():
        try:
            if not _has_eligible_model():
                _agent_stop.wait(30)
                continue
            result = process_inbox_once()
            if result.get("processed"):
                logger.info("Department inbox supervisor processed %s message(s), queued %s internal task(s).",
                            result.get("processed"), result.get("tasks_created"))
            else:
                _agent_stop.wait(5)
        except Exception:
            logger.exception("Department inbox supervisor recovered from an error.")
            _agent_stop.wait(10)


def _discovery_worker_loop() -> None:
    logger.info("Technology discovery worker started in API service.")
    while not _discovery_stop.is_set():
        try:
            processed = run_discovery_pending_once()
            if not processed:
                _discovery_stop.wait(5)
        except Exception:
            logger.exception("Technology discovery worker recovered from an error.")
            _discovery_stop.wait(5)
    logger.info("Technology discovery worker stopped.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _discovery_thread, _agent_thread, _learning_thread, _inbox_thread, _executive_thread
    settings = get_settings()
    if settings.environment != "development" and not settings.api_key:
        raise RuntimeError("AI_OS_API_KEY must be set outside development.")
    initialize_database()
    refresh_business_ids()
    _discovery_stop.clear()
    _discovery_thread = threading.Thread(
        target=_discovery_worker_loop,
        name="aios-discovery-worker",
        daemon=True,
    )
    _discovery_thread.start()

    # Production runs the bounded worker in this same single-replica service.
    # This avoids a second Railway service needing to share the SQLite volume.
    import os
    embedded_worker = settings.environment == "development" or os.getenv("AI_OS_EMBEDDED_WORKER", "false").strip().casefold() in {"1", "true", "yes", "on"}
    if embedded_worker:
        _agent_stop.clear()
        _agent_thread = threading.Thread(target=_agent_worker_loop, name="aios-agent-worker", daemon=True)
        _learning_thread = threading.Thread(target=_brain_learning_loop, name="aios-brain-learning", daemon=True)
        _inbox_thread = threading.Thread(target=_inbox_worker_loop, name="aios-inbox-supervisor", daemon=True)
        _executive_thread = threading.Thread(
            target=executive_supervisor_loop, args=(_agent_stop, 15),
            name="aios-executive-supervisor", daemon=True,
        )
        for thread in (_agent_thread, _learning_thread, _inbox_thread, _executive_thread):
            thread.start()
        logger.info("Embedded AIOS worker suite started; one service replica and shared persistent volume are required.")

    try:
        yield
    finally:
        _discovery_stop.set()
        _agent_stop.set()
        for thread in (_agent_thread, _learning_thread, _inbox_thread, _executive_thread, _discovery_thread):
            if thread is not None:
                thread.join(timeout=10)
        _agent_thread = _learning_thread = _inbox_thread = _executive_thread = _discovery_thread = None


app = FastAPI(
    title="AI Operating System",
    version="0.1.0",
    description="Human-supervised AI company workflow foundation.",
    lifespan=lifespan,
)


@app.get("/owner", include_in_schema=False)
def get_owner_dashboard():
    return owner_dashboard()


class OwnerLoginRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


@app.post("/auth/session")
def create_session(payload: OwnerLoginRequest, response: Response):
    try:
        token, expires_at = create_owner_session(payload.api_key)
    except HTTPException:
        raise
    response.set_cookie(
        key=SESSION_COOKIE, value=token, max_age=SESSION_TTL_DAYS * 86400,
        httponly=True, secure=True, samesite="strict", path="/",
    )
    return {"authenticated": True, "expires_at": expires_at, "session_days": SESSION_TTL_DAYS}


@app.delete("/auth/session")
def delete_session(request: Request, response: Response):
    revoke_owner_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(key=SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return {"authenticated": False}


@app.get("/auth/session")
def session_status(request: Request):
    # This endpoint intentionally returns status only; no session token or API key is exposed.
    from ai_os.auth import _valid_session
    return {"authenticated": _valid_session(request)}


class ModelRunRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=8000)


class ResearchSourceRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    business_id: str = Field(default="core", min_length=1, max_length=64)


class BrainMemoryReview(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(default="", max_length=1000)


class VentureOpportunityCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    thesis: str = Field(min_length=20, max_length=6000)
    customer_segment: str = Field(default="", max_length=500)
    problem: str = Field(default="", max_length=1000)
    revenue_model: str = Field(default="unknown", max_length=100)
    market_scope: str = Field(default="global", max_length=120)


class VentureAssessmentRequest(BaseModel):
    assessment: dict = Field(default_factory=dict)
    evidence: list[dict] = Field(default_factory=list, max_length=100)


class VentureDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(shortlisted|launch_approved|rejected|paused)$")
    notes: str = Field(default="", max_length=3000)


class CodeEvolutionRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=5000)
    target_path: str = Field(min_length=1, max_length=300)


class OpenRouterCredentialRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    confirm_free_only: bool


class ProviderCredentialRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    model: str = Field(default="__catalog_only__", max_length=200)
    confirm_free_only: bool


class ProviderModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    confirm_free_only: bool


class BusinessIntegrationRequest(BaseModel):
    secret: str = Field(min_length=8, max_length=4096)
    config: dict = Field(default_factory=dict)


@app.get("/business-integrations/{business_id}", dependencies=[Depends(require_owner_key)])
def get_business_integrations(business_id: str):
    if business_id not in BUSINESS_IDS or business_id == "core":
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    try:
        return {"business_id": business_id, "integrations": business_integration_statuses(business_id),
                "security": "Encrypted at rest; secret values are never returned by this API."}
    except CredentialVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/business-integrations/{business_id}/{provider}", dependencies=[Depends(require_owner_key)])
def post_business_integration(business_id: str, provider: str, payload: BusinessIntegrationRequest):
    try:
        return save_business_integration(business_id, provider, payload.secret, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CredentialVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/business-integrations/{business_id}/{provider}/connect", dependencies=[Depends(require_owner_key)])
def connect_business_integration(business_id: str, provider: str, payload: BusinessIntegrationRequest):
    """Verify owner-supplied credentials with a read-only platform request before storing."""
    try:
        if provider == "playerauctions":
            verification = marketplace_integrations.verify_playerauctions(payload.secret, payload.config)
        elif provider in {"wordpress", "woocommerce"}:
            verification = platform_integrations.verify_connection(provider, payload.secret, payload.config)
        else:
            raise HTTPException(status_code=422, detail="This provider does not yet have a supported direct account connection flow.")
        saved = save_business_integration(business_id, provider, payload.secret, payload.config)
        return {**saved, "verification": verification, "external_actions": "read-only verification only"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (platform_integrations.IntegrationCheckError, marketplace_integrations.MarketplaceCheckError, social_oauth.OAuthError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except CredentialVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/business-integrations/social/status", dependencies=[Depends(require_owner_key)])
def get_social_oauth_status():
    return {"providers": social_oauth.readiness(),
            "security": "OAuth app secrets remain server-side; account tokens are encrypted in the business vault."}


@app.post("/business-integrations/{business_id}/social/{provider}/start", dependencies=[Depends(require_owner_key)])
def start_social_oauth(business_id: str, provider: str):
    try:
        return {"provider": provider, "authorize_url": social_oauth.begin(provider, business_id),
                "scopes": social_oauth.PROVIDERS[provider]["scopes"],
                "external_actions": "authorization only; read-oriented scopes"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (social_oauth.OAuthError, CredentialVaultUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/business-integrations/social/{provider}/callback", response_class=HTMLResponse)
def complete_social_oauth(provider: str, code: str = Query(default="", max_length=4096),
                          state: str = Query(default="", max_length=256),
                          error: str = Query(default="", max_length=300)):
    if error:
        return HTMLResponse("<h2>Account connection was cancelled or rejected.</h2><p>Return to the AIOS owner dashboard and try again if intended.</p>", status_code=400)
    try:
        result = social_oauth.complete(provider, state, code)
        return HTMLResponse("<h2>Account connected successfully</h2><p>" +
            escape(result["provider"]) + " · " + escape(result["account"]) +
            "</p><p>Return to the AIOS owner dashboard and refresh the account list.</p>")
    except (ValueError, social_oauth.OAuthError, CredentialVaultUnavailable) as exc:
        return HTMLResponse("<h2>Account connection failed</h2><p>" +
            str(exc).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") +
            "</p><p>No publishing or other external action was performed.</p>", status_code=400)


@app.post("/business-integrations/{business_id}/{provider}/test", dependencies=[Depends(require_owner_key)])
def test_business_integration(business_id: str, provider: str):
    """Recheck an already saved platform credential without exposing it."""
    try:
        credential = get_business_integration_credential(business_id, provider)
        if credential is None:
            raise HTTPException(status_code=404, detail="No saved platform connection.")
        if provider == "playerauctions":
            verification = marketplace_integrations.verify_playerauctions(credential["secret"], credential["config"])
        elif provider == "etsy":
            verification = social_oauth.verify_etsy_credential(credential["secret"], credential["config"], business_id)
        elif provider in social_oauth.PROVIDERS:
            verification = social_oauth.verify_social_credential(provider, credential["secret"], credential["config"], business_id)
        else:
            verification = platform_integrations.verify_connection(provider, credential["secret"], credential["config"])
        return {**verification, "external_actions": "read-only verification only"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (platform_integrations.IntegrationCheckError, marketplace_integrations.MarketplaceCheckError, social_oauth.OAuthError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except CredentialVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.delete("/business-integrations/{business_id}/{provider}", dependencies=[Depends(require_owner_key)])
def delete_business_integration_route(business_id: str, provider: str):
    try:
        deleted = delete_business_integration(business_id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Business integration credential not found.")
    return {"business_id": business_id, "provider": provider, "deleted": True}


@app.get("/llm/credentials", dependencies=[Depends(require_owner_key)])
def get_llm_credentials():
    return {"openrouter": credential_status(), "providers": provider_credential_statuses()}


@app.post("/llm/credentials/openrouter", dependencies=[Depends(require_owner_key)])
def post_openrouter_credentials(payload: OpenRouterCredentialRequest):
    try:
        save_openrouter(payload.api_key, payload.confirm_free_only)
        return {"saved": True, "provider": "openrouter", "storage": "encrypted"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CredentialVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/llm/credentials/{provider_id}", dependencies=[Depends(require_owner_key)])
def post_provider_credentials(provider_id: str, payload: ProviderCredentialRequest):
    try:
        save_provider_credential(provider_id, payload.api_key, payload.model, payload.confirm_free_only)
        return {"saved": True, "provider": provider_id, "storage": "encrypted"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CredentialVaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/llm/credentials/{provider_id}/model", dependencies=[Depends(require_owner_key)])
def post_provider_model(provider_id: str, payload: ProviderModelRequest):
    try:
        update_provider_model(provider_id, payload.model, payload.confirm_free_only)
        return {"saved": True, "provider": provider_id, "model": payload.model,
                "free_only_routing": payload.confirm_free_only}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



@app.get("/llm/providers", dependencies=[Depends(require_api_key)])
def get_llm_providers():
    return list_providers()


@app.get("/llm/unorouter/catalog", dependencies=[Depends(require_owner_key)])
def get_unorouter_catalog():
    """Read-only public pricing catalogue and exact models allowed by saved key."""
    try:
        return list_unorouter_catalog()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/llm/unorouter/personal-test", dependencies=[Depends(require_owner_key)])
def post_unorouter_personal_test(payload: ModelRunRequest):
    """Owner-only consumer-account experiment; deliberately outside company routing."""
    try:
        return test_unorouter_personal(payload.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/llm/test", dependencies=[Depends(require_api_key)])
def post_llm_test(payload: ModelRunRequest):
    try:
        if payload.provider == "auto":
            result = generate_with_fallback("Reply with exactly: AIOS live connection successful")
            result["test_passed"] = result["response"].strip().lower().startswith("aios live connection successful")
            return result
        return test_provider(payload.provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/llm/run", dependencies=[Depends(require_api_key)])
def post_llm_run(payload: ModelRunRequest):
    try:
        return generate_with_fallback(payload.prompt) if payload.provider == "auto" else generate(payload.provider, payload.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc



@app.get("/company/departments", dependencies=[Depends(require_api_key)])
def get_company_departments():
    """Return the business department registry enriched with source-catalogue counts."""
    registry_path = Path(__file__).resolve().parents[2] / "data" / "company_departments.json"
    manifest_path = Path(__file__).resolve().parents[2] / "data" / "agency_agents_manifest.json"
    if not registry_path.exists() or not manifest_path.exists():
        raise HTTPException(status_code=503, detail="Company department registry or workforce manifest is unavailable.")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_counts = {item["id"]: item["agent_count"] for item in manifest.get("departments", [])}
    departments = []
    for item in registry.get("departments", []):
        specialist_count = sum(source_counts.get(source, 0) for source in item.get("source_departments", []))
        departments.append({
            **item,
            "specialist_count": specialist_count,
            "roles_available": specialist_count > 0 or bool(item.get("built_in_roles")),
            "execution_status": "available-on-demand" if specialist_count > 0 or item.get("built_in_roles") else "not-catalogued",
            "workflow_status": "sequential-workflow-with-persisted-inbox-handoffs",
        })
    return {
        "department_count": len(departments),
        "source_department_count": manifest.get("department_count", 0),
        "catalogued_agent_count": manifest.get("agent_count", 0),
        "runtime_model": "one shared worker invokes selected specialist instructions on demand; no dedicated always-on department processes",
        "departments": departments,
    }


@app.get("/workforce/agents", dependencies=[Depends(require_api_key)])
def get_workforce_agents(department: str | None = None, q: str | None = None):
    """Return the complete catalogued Agency workforce; catalog entries are not live workers."""
    manifest_path = Path(__file__).resolve().parents[2] / "data" / "agency_agents_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=503, detail="Workforce manifest is unavailable.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agents = manifest["agents"]
    if department:
        agents = [a for a in agents if a["department"] == department]
    if q:
        term = q.casefold()
        agents = [a for a in agents if term in a["name"].casefold() or term in a["department"].casefold() or term in a["id"].casefold()]
    return {
        "source_repository": manifest["source_repository"],
        "license": manifest["license"],
        "agent_count": manifest["agent_count"],
        "department_count": manifest["department_count"],
        "roles_including_ceo": manifest["roles_including_ceo"],
        "departments": manifest["departments"],
        "catalog_status": "on-demand-invocation",
        "runtime_model": "one shared worker invokes selected role instructions per task; roles are not resident processes",
        "agents": [{**a, "execution_status": "available-on-demand"} for a in agents],
    }



@app.get("/company/sources", dependencies=[Depends(require_api_key)])
def get_company_sources():
    manifest_path = Path(__file__).resolve().parents[2] / "data" / "repository_sources.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=503, detail="Repository source inventory is unavailable.")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@app.get("/company/overview", dependencies=[Depends(require_api_key)])
def get_company_overview():
    with connect() as db:
        tasks = db.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall()
        approvals = db.execute("SELECT status, COUNT(*) AS n FROM approvals GROUP BY status").fetchall()
        scans = db.execute("SELECT status, COUNT(*) AS n FROM discovery_scans GROUP BY status").fetchall()
        candidates = db.execute("SELECT COUNT(*) AS n FROM discovery_candidates").fetchone()["n"]
        agent_runs = db.execute("SELECT status, COUNT(*) AS n FROM agent_runs GROUP BY status").fetchall()
    return {
        "workforce": {"agents": 283, "departments": 18, "company_departments": 12, "roles_including_ceo": 284, "runtime_ready": bool(_agent_thread and _agent_thread.is_alive()), "runtime_scope": "shared on-demand specialist invocation plus CEO review; no external side effects"},
        "tasks": {r["status"]: r["n"] for r in tasks},
        "approvals": {r["status"]: r["n"] for r in approvals},
        "discovery_scans": {r["status"]: r["n"] for r in scans},
        "discovered_repositories": candidates,
        "agent_runs": {r["status"]: r["n"] for r in agent_runs},
        "execution_runtime": "shared-worker-on-demand-specialist-plus-ceo-review",
        "agent_worker_running": bool(_agent_thread and _agent_thread.is_alive()),
    }


@app.get("/research/sources", dependencies=[Depends(require_api_key)])
def get_research_sources(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return list_sources(business_id=business_id)


@app.post("/research/sources", status_code=201, dependencies=[Depends(require_owner_key)])
def post_research_source(payload: ResearchSourceRequest):
    """Owner-triggered read-only capture of one public HTTPS research page."""
    try:
        # Strip invisible Unicode formatting/control characters at the API boundary too;
        # mobile copy/paste can append U+2060 WORD JOINER without displaying it.
        submitted_url = unicodedata.normalize("NFC", payload.url)
        submitted_url = "".join(
            ch for ch in submitted_url
            if unicodedata.category(ch) not in {"Cf", "Cc", "Cs", "Zl", "Zp"}
        ).strip()
        return capture_source(submitted_url, payload.business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnicodeError as exc:
        raise HTTPException(status_code=422, detail="The URL contains unsupported invisible or non-ASCII characters. Remove hidden formatting characters and try again.") from exc


@app.get("/business-environments", dependencies=[Depends(require_api_key)])
def get_business_environments():
    return {
        "company_goal": "Discover, validate, launch and grow any legitimate profitable business opportunity.",
        "shared_core": "One shared reasoning/model platform and reusable technical capabilities; business memories, customers, finances and credentials remain isolated.",
        "environments": list_businesses(),
        "memory_isolation": "Exact business_id scope; no cross-business memory fallback.",
        "expansion": "New ventures can be registered as separate business units without changing the core company architecture.",
    }


class BusinessUnitCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    business_type: str = Field(default="general", min_length=2, max_length=64)
    description: str = Field(default="", max_length=3000)


@app.get("/business-units", dependencies=[Depends(require_api_key)])
def get_business_units():
    return {"business_units": list_businesses()}


@app.post("/business-units", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_unit(payload: BusinessUnitCreate):
    try:
        from ai_os.business_registry import create_business
        return create_business(payload.name, payload.business_type, payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/code-evolution/status", dependencies=[Depends(require_owner_key)])
def get_code_evolution_status():
    """Report whether guarded branch-only AI code evolution is configured."""
    return code_evolution.readiness()


@app.post("/code-evolution/proposals", dependencies=[Depends(require_owner_key)])
def post_code_evolution_proposal(payload: CodeEvolutionRequest):
    """Generate one allowlisted code change in a new branch and open a draft PR."""
    try:
        return code_evolution.create_proposal(payload.objective, payload.target_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except code_evolution.CodeEvolutionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/brain/status", dependencies=[Depends(require_api_key)])
def get_brain_status(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return brain_status(business_id)


@app.post("/brain/learn", dependencies=[Depends(require_owner_key)])
def post_brain_learning_cycle(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    try:
        return run_learning_cycle(business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/brain/memories", dependencies=[Depends(require_api_key)])
def get_brain_memories(status: str | None = None, limit: int = 100, business_id: str = "core"):
    if status is not None and status not in {"proposed", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Invalid memory status.")
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return list_memories(status, limit, business_id)


@app.post("/brain/memories/{memory_id}/review", dependencies=[Depends(require_owner_key)])
def post_brain_memory_review(memory_id: str, payload: BrainMemoryReview):
    try:
        result = review_memory(memory_id, payload.decision, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Proposed memory not found or already reviewed.")
    return result



@app.get("/company/collaboration/messages", dependencies=[Depends(require_api_key)])
def get_department_messages(business_id: str = "core", department: str | None = None,
                            status: str | None = None, limit: int = 100):
    try: return list_messages(business_id,department,status,limit)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.post("/company/collaboration/messages", status_code=201, dependencies=[Depends(require_owner_key)])
def post_department_message(payload: DepartmentMessageRequest):
    try:
        return send_message(payload.business_id,payload.sender_department,payload.recipient_department,
                            payload.subject,payload.body,payload.related_task_id)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    except LookupError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc


@app.post("/company/collaboration/messages/{message_id}/read", dependencies=[Depends(require_owner_key)])
def post_department_message_read(message_id: str, business_id: str, department: str):
    try: result=mark_message_read(message_id,business_id,department)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    if result is None: raise HTTPException(status_code=404,detail="Message not found in this department inbox.")
    return result


@app.get("/company/collaboration/delegations", dependencies=[Depends(require_api_key)])
def get_department_delegations(business_id: str = "core", department: str | None = None, limit: int = 100):
    try: return list_delegations(business_id,department,limit)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.post("/company/collaboration/delegations", status_code=201, dependencies=[Depends(require_owner_key)])
def post_department_delegation(payload: DepartmentDelegationRequest):
    try:
        return delegate_task(payload.business_id,payload.from_department,payload.to_department,
                             payload.title,payload.description,payload.parent_task_id)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    except LookupError as exc: raise HTTPException(status_code=404,detail=str(exc)) from exc



@app.get("/company/executive/status", dependencies=[Depends(require_api_key)])
def get_executive_status(business_id: str | None = None):
    """Read executive metrics and alerts, optionally scoped to one business."""
    try:
        return executive_status(business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/company/executive/supervise", dependencies=[Depends(require_owner_key)])
def post_executive_supervise():
    """Owner-triggered reconciliation of failures and workflow blockers."""
    return supervise_once()


@app.get("/company/workflows", dependencies=[Depends(require_api_key)])
def get_workflow_templates():
    """List available gated department workflow templates."""
    return list_templates()


@app.post("/company/workflows/{template_id}/start", status_code=201, dependencies=[Depends(require_owner_key)])
def post_start_workflow(template_id: str, business_id: str = "core"):
    """Create a persisted workflow; only its first task is queued."""
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    try:
        return create_workflow(template_id, business_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/company/workflows/instances", dependencies=[Depends(require_api_key)])
def get_workflow_instances(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return list_workflows(business_id=business_id)


@app.get("/company/workflows/{workflow_id}", dependencies=[Depends(require_api_key)])
def get_workflow_detail(workflow_id: str, business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    result = get_workflow(workflow_id)
    if result is None or result.get("business_id") != business_id:
        raise HTTPException(status_code=404, detail="Workflow not found in this business environment.")
    return result



class BusinessRecordRequest(BaseModel):
    business_id: str = Field(default="core", min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    amount: float | None = Field(default=None, ge=0, le=1000000000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    contact: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    verified_payment: bool = False


class InvestorRequest(BaseModel):
    business_id: str = Field(default="core", min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=180)
    organization: str = Field(default="", max_length=180)
    contact: str = Field(default="", max_length=200)
    stage: str = Field(default="prospect", max_length=40)
    notes: str = Field(default="", max_length=2000)


class CodeAssetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    repository_url: str = Field(default="", max_length=2048)
    path: str = Field(default="", max_length=500)
    asset_type: str = Field(default="source_code", max_length=50)
    ownership_status: str = Field(default="unverified", max_length=50)
    license: str = Field(default="unknown", max_length=100)
    dependency_review: str = Field(default="not_reviewed", max_length=50)
    token_estimate: int | None = Field(default=None, ge=0)
    token_method: str = Field(default="not_measured", max_length=100)
    notes: str = Field(default="", max_length=2000)


class LicenseOfferRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=80)
    buyer: str = Field(min_length=1, max_length=180)
    terms: str = Field(min_length=1, max_length=3000)


@app.get("/business/summary", dependencies=[Depends(require_api_key)])
def get_business_summary(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return business_ops.business_summary(business_id)


@app.get("/business/customers", dependencies=[Depends(require_api_key)])
def get_business_customers(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return business_ops.list_records("customer", business_id=business_id)


@app.post("/business/customers", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_customer(payload: BusinessRecordRequest):
    try:
        return business_ops.create_record("customer", payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/business/expenses", dependencies=[Depends(require_api_key)])
def get_business_expenses(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return business_ops.list_records("expense", business_id=business_id)


@app.post("/business/expenses", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_expense(payload: BusinessRecordRequest):
    try:
        return business_ops.create_record("expense", payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/business/revenue", dependencies=[Depends(require_api_key)])
def get_business_revenue(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return business_ops.list_records("revenue", business_id=business_id)


@app.post("/business/revenue", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_revenue(payload: BusinessRecordRequest):
    try:
        return business_ops.create_record("revenue", payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/business/investors", dependencies=[Depends(require_api_key)])
def get_business_investors(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return business_ops.list_investors(business_id=business_id)


@app.post("/business/investors", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_investor(payload: InvestorRequest):
    try:
        return business_ops.create_investor(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/code-assets", dependencies=[Depends(require_api_key)])
def get_code_assets():
    return business_ops.list_assets()


@app.post("/code-assets", status_code=201, dependencies=[Depends(require_owner_key)])
def post_code_asset(payload: CodeAssetRequest):
    try:
        return business_ops.create_asset(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/code-assets/license-offers", dependencies=[Depends(require_api_key)])
def get_code_license_offers():
    return business_ops.list_license_offers()


@app.post("/code-assets/license-offers", status_code=201, dependencies=[Depends(require_owner_key)])
def post_code_license_offer(payload: LicenseOfferRequest):
    try:
        return business_ops.create_license_offer(payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-operating-system"}


@app.post("/tasks", response_model=TaskOut, status_code=201, dependencies=[Depends(require_api_key)])
def post_task(payload: TaskCreate):
    try:
        return create_task(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/tasks", response_model=list[TaskOut], dependencies=[Depends(require_api_key)])
def get_tasks(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return list_tasks(business_id)


@app.post("/tasks/{task_id}/execute", status_code=202, dependencies=[Depends(require_api_key)])
def execute_task(task_id: str, business_id: str = "core"):
    _require_task_business_scope(task_id, business_id)
    try:
        if not task_is_runnable(task_id):
            raise ValueError("This workflow step is blocked until the previous department step completes.")
        return create_run(task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/agent-runs/{run_id}/retry", status_code=202, dependencies=[Depends(require_api_key)])
def retry_agent_run(run_id: str, business_id: str):
    _require_run_business_scope(run_id, business_id)
    try:
        return retry_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/agent-runs", dependencies=[Depends(require_api_key)])
def get_agent_runs(task_id: str | None = None, business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return list_runs(task_id, business_id)


def _require_task_business_scope(task_id: str, business_id: str) -> dict:
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    with connect() as db:
        row = db.execute(
            "SELECT * FROM tasks WHERE id=? AND business_id=?",
            (task_id, business_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found in this business environment.")
    return dict(row)


def _require_run_business_scope(run_id: str, business_id: str) -> dict:
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    with connect() as db:
        row = db.execute(
            """SELECT r.id FROM agent_runs r
            JOIN tasks t ON t.id=r.task_id
            WHERE r.id=? AND t.business_id=?""",
            (run_id, business_id),
        ).fetchone()
    if row is None:
        # Do not disclose whether a run exists in another business environment.
        raise HTTPException(status_code=404, detail="Agent run not found in this business environment.")
    result = get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return result


@app.get("/agent-runs/{run_id}", dependencies=[Depends(require_api_key)])
def get_agent_run(run_id: str, business_id: str = "core"):
    return _require_run_business_scope(run_id, business_id)


@app.get("/agent-runs/{run_id}/events", dependencies=[Depends(require_api_key)])
def get_agent_run_events(run_id: str, business_id: str = "core"):
    """Return the persisted execution timeline only within its selected business."""
    _require_run_business_scope(run_id, business_id)
    with connect() as db:
        rows = db.execute(
            "SELECT id, stage, message, created_at FROM agent_run_events WHERE run_id=? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]

@app.get("/agent-runs/{run_id}/steps", dependencies=[Depends(require_api_key)])
def get_agent_run_steps(run_id: str, business_id: str = "core"):
    """Return agent contributions only within the selected business."""
    _require_run_business_scope(run_id, business_id)
    with connect() as db:
        rows = db.execute(
            """SELECT sequence_no, role, agent_id, agent_name, status,
            input_summary, output, error, created_at, finished_at
            FROM agent_run_steps WHERE run_id=? ORDER BY sequence_no ASC""",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post(
    "/approvals",
    response_model=ApprovalOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def post_approval(payload: ApprovalCreate):
    try:
        return create_approval(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/approvals",
    response_model=list[ApprovalOut],
    dependencies=[Depends(require_api_key)],
)
def get_approvals(business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    return list_approvals(business_id)


@app.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalOut,
    dependencies=[Depends(require_api_key)],
)
def post_approval_decision(approval_id: str, payload: ApprovalDecision, business_id: str = "core"):
    if business_id not in BUSINESS_IDS:
        raise HTTPException(status_code=422, detail="Unknown business environment.")
    with connect() as db:
        scoped = db.execute(
            "SELECT 1 FROM approvals WHERE id=? AND business_id=?",
            (approval_id, business_id),
        ).fetchone()
    if scoped is None:
        raise HTTPException(status_code=404, detail="Approval request not found in this business environment.")
    try:
        result = decide_approval(approval_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    business_ops.apply_expense_approval(approval_id, payload.decision)
    return result


@app.get("/venture-opportunities", dependencies=[Depends(require_api_key)])
def get_venture_opportunities(status: str | None = None):
    if status and status not in venture_pipeline.STATUSES:
        raise HTTPException(status_code=422, detail="Unknown opportunity status.")
    return venture_pipeline.list_opportunities(status)


@app.get("/venture-opportunities/{opportunity_id}", dependencies=[Depends(require_api_key)])
def get_venture_opportunity(opportunity_id: str):
    result = venture_pipeline.get_opportunity(opportunity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    return result


@app.post("/venture-opportunities", status_code=201, dependencies=[Depends(require_owner_key)])
def post_venture_opportunity(payload: VentureOpportunityCreate):
    try:
        return venture_pipeline.create_opportunity(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/venture-opportunities/{opportunity_id}/research", status_code=202, dependencies=[Depends(require_owner_key)])
def post_venture_research(opportunity_id: str):
    opportunity = venture_pipeline.get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    description = (
        "COMPANY-WIDE VENTURE OPPORTUNITY RESEARCH. This is portfolio research, not work for an existing business unit. "
        "Do not assume the opportunity is viable. Research the thesis, target customer, problem severity and willingness to pay; "
        "market size with sourced methodology; competitors and substitutes; pricing and revenue model; startup and recurring costs; "
        "unit economics and break-even assumptions; distribution channels and acquisition costs; operational feasibility; "
        "legal/regulatory/IP risks; and a low-cost validation experiment. Compare at least three credible source URLs where possible. "
        "Separate dated sourced facts, estimates, hypotheses and unknowns. Never invent figures, sources, customer demand or profit. "
        "Return the six-dimension 0-5 scorecard (demand, competition, economics, distribution, execution, risk), explain every rating, "
        "include HTTPS source URLs and dates, give conservative/base/upside economics only when assumptions are explicit, and recommend "
        "validate, defer or reject. No spending, publishing, customer commitments or account changes.\n\n"
        f"OPPORTUNITY: {opportunity['title']}\nTHESIS: {opportunity['thesis']}\n"
        f"CUSTOMER SEGMENT: {opportunity['customer_segment']}\nPROBLEM: {opportunity['problem']}\n"
        f"REVENUE MODEL: {opportunity['revenue_model']}\nMARKET SCOPE: {opportunity['market_scope']}\n"
    )
    previous_status = None
    try:
        previous_status = venture_pipeline.reserve_research(opportunity_id)
        task = create_task(TaskCreate(
            title="Venture research: " + opportunity["title"][:150],
            description=description,
            department="venture-strategy",
            business_id="core",
        ))
        run = create_run(task["id"])
        result = venture_pipeline.attach_research_task(opportunity_id, task["id"])
        return {"opportunity": result, "task": task, "agent_run": run,
                "execution_policy": "Free-confirmed models only; no paid fallback; no external side effects."}
    except (ValueError, LookupError) as exc:
        if previous_status is not None:
            venture_pipeline.cancel_research_reservation(opportunity_id, previous_status)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        if previous_status is not None:
            venture_pipeline.cancel_research_reservation(opportunity_id, previous_status)
        raise


@app.get("/venture-opportunities/{opportunity_id}/research-report", dependencies=[Depends(require_owner_key)])
def get_venture_research_report(opportunity_id: str):
    try:
        result = venture_pipeline.get_research_report(opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    return result


@app.post("/venture-opportunities/{opportunity_id}/assessment", dependencies=[Depends(require_owner_key)])
def post_venture_assessment(opportunity_id: str, payload: VentureAssessmentRequest):
    try:
        return venture_pipeline.save_assessment(opportunity_id, payload.assessment, payload.evidence)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/venture-opportunities/{opportunity_id}/decision", dependencies=[Depends(require_owner_key)])
def post_venture_decision(opportunity_id: str, payload: VentureDecisionRequest):
    try:
        return venture_pipeline.decide_opportunity(opportunity_id, payload.decision, payload.notes)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/venture-opportunities/{opportunity_id}/launch", status_code=201, dependencies=[Depends(require_owner_key)])
def post_launch_venture(opportunity_id: str):
    opportunity = venture_pipeline.get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    if opportunity["status"] != "launch_approved":
        raise HTTPException(status_code=409, detail="Owner launch approval is required before creating a business unit.")
    revenue_model = opportunity["revenue_model"].lower()
    business_type = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in revenue_model).strip("-")[:60].strip("-")
    if len(business_type) < 3:
        business_type = "general"
    try:
        business = create_business(
            opportunity["title"],
            business_type,
            "Created from owner-approved venture opportunity. " + opportunity["thesis"],
        )
        result = venture_pipeline.mark_launched(opportunity_id, business["id"])
        return {"opportunity": result, "business_unit": business,
                "side_effects": "A separate business unit was registered. No money was spent, no listings were published, and no external account or customer was contacted."}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/discovery/status", dependencies=[Depends(require_api_key)])
def get_discovery_status():
    """Live connectivity and worker diagnostic; never returns the GitHub token."""
    github = github_api_status()
    return {
        "github": github,
        "worker_running": bool(_discovery_thread and _discovery_thread.is_alive()),
        "scope": "public GitHub repository metadata; no code execution or installation",
    }


@app.get("/discovery/provider-catalog", dependencies=[Depends(require_api_key)])
def get_free_api_catalog(category: str | None = None):
    return list_free_api_catalog(category)


@app.post("/discovery/provider-catalog/sync", dependencies=[Depends(require_owner_key)])
def post_free_api_catalog_sync():
    try:
        return sync_free_api_catalog()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Free API catalog sync failed: {exc}") from exc


@app.post("/discovery/scans", status_code=202, dependencies=[Depends(require_api_key)])
def post_discovery_scan(payload: DiscoveryScanCreate):
    try:
        return create_scan(payload.categories)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/discovery/scans", dependencies=[Depends(require_api_key)])
def get_discovery_scans():
    return list_scans()


@app.get("/discovery/candidates", dependencies=[Depends(require_api_key)])
def get_discovery_candidates():
    return list_candidates()


@app.post("/discovery/candidates/review", dependencies=[Depends(require_owner_key)])
def post_candidate_review(payload: CandidateReviewDecision):
    """Record an owner decision; sandbox approval does not install or execute code."""
    url = payload.repository_url.strip()
    if not url.startswith("https://github.com/"):
        raise HTTPException(status_code=422, detail="Only canonical HTTPS GitHub repository URLs can be reviewed.")
    with connect() as db:
        row = db.execute("SELECT canonical_url FROM discovery_candidates WHERE canonical_url=?", (url,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Discovery candidate not found.")
        updated = datetime.now(timezone.utc).isoformat()
        db.execute(
            "UPDATE discovery_candidates SET review_state=?, review_notes=?, review_updated_at=? WHERE canonical_url=?",
            (payload.decision, payload.notes.strip(), updated, url),
        )
    return {"repository_url": url, "review_state": payload.decision, "review_notes": payload.notes.strip(), "review_updated_at": updated, "side_effects": "none"}




class WebsiteApiCallRequest(BaseModel):
    args: dict = Field(default_factory=dict)
    fields: list[str] | None = None


@app.get("/integrations/api-anything/status", dependencies=[Depends(require_owner_key)])
def get_api_anything_status():
    return website_api.status()


@app.get("/integrations/api-anything/sites", dependencies=[Depends(require_owner_key)])
def get_api_anything_sites():
    try:
        return website_api.list_sites()
    except website_api.WebsiteApiUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/integrations/api-anything/sites/{site}", dependencies=[Depends(require_owner_key)])
def get_api_anything_site_operations(site: str):
    try:
        return website_api.list_operations(site)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except website_api.WebsiteApiUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/integrations/api-anything/find", dependencies=[Depends(require_owner_key)])
def find_api_anything_sites(q: str = Query(min_length=1, max_length=300)):
    try:
        return website_api.find_sites(q)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except website_api.WebsiteApiUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/integrations/api-anything/call/{site}/{operation}", dependencies=[Depends(require_owner_key)])
def call_api_anything_read(site: str, operation: str, payload: WebsiteApiCallRequest):
    """Owner-triggered read only. The bridge never exposes API Anything's write endpoint."""
    try:
        return website_api.call_read(site, operation, payload.args, payload.fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except website_api.WebsiteApiUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# Owner-only Supabase diagnostics; the router never exposes credentials or applies migrations.
from ai_os.supabase_integration import router as supabase_router
app.include_router(supabase_router)
