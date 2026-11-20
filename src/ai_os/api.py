"""FastAPI application."""
from contextlib import asynccontextmanager
import logging
import threading
import unicodedata
import json
import hmac
import os
import time
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse
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
from ai_os.agent_runtime import create_run, get_run, list_runs, retry_run, recover_interrupted_runs, run_pending_once as run_agent_pending_once
from ai_os.credentials import save_openrouter, credential_status, CredentialVaultUnavailable, save_provider_credential, update_provider_model, provider_credential_statuses
from ai_os.brain import brain_status, list_memories, review_memory
from ai_os.workflows import list_templates, create_workflow, get_workflow, list_workflows, task_is_runnable
from ai_os.research_sources import capture_source, list_sources
from ai_os import website_api
from ai_os import business_ops
from ai_os import social_media
from ai_os import video_jobs
from pydantic import BaseModel, Field


logger = logging.getLogger("ai_os.api")
_discovery_stop = threading.Event()
_discovery_thread: threading.Thread | None = None
_agent_stop = threading.Event()
_agent_thread: threading.Thread | None = None


def _agent_worker_loop() -> None:
    logger.info("Bounded agent execution worker started.")
    while not _agent_stop.is_set():
        try:
            if not run_agent_pending_once():
                _agent_stop.wait(3)
        except Exception:
            logger.exception("Agent worker recovered from an error.")
            _agent_stop.wait(3)
    logger.info("Bounded agent execution worker stopped.")


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
    global _discovery_thread, _agent_thread
    settings = get_settings()
    if settings.environment != "development" and not settings.api_key:
        raise RuntimeError("AI_OS_API_KEY must be set outside development.")
    initialize_database()
    # This service is intentionally deployed as one worker replica. A process restart
    # must not leave runs permanently marked as running.
    recover_interrupted_runs()
    _discovery_stop.clear()
    _discovery_thread = threading.Thread(
        target=_discovery_worker_loop,
        name="aios-discovery-worker",
        daemon=True,
    )
    _discovery_thread.start()
    _agent_stop.clear()
    _agent_thread = threading.Thread(
        target=_agent_worker_loop,
        name="aios-agent-worker",
        daemon=True,
    )
    _agent_thread.start()
    try:
        yield
    finally:
        _discovery_stop.set()
        _agent_stop.set()
        if _agent_thread is not None:
            _agent_thread.join(timeout=10)
            _agent_thread = None
        if _discovery_thread is not None:
            _discovery_thread.join(timeout=10)
            _discovery_thread = None


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
    approve_paid_request: bool = False


class ResearchSourceRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)


class BrainMemoryReview(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(default="", max_length=1000)


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
        return test_unorouter_personal(payload.prompt, payload.approve_paid_request)
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
            "workflow_status": item.get("workflow_state", "catalogue-only"),
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
def get_research_sources():
    return list_sources()


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
        return capture_source(submitted_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnicodeError as exc:
        raise HTTPException(status_code=422, detail="The URL contains unsupported invisible or non-ASCII characters. Remove hidden formatting characters and try again.") from exc


@app.get("/brain/status", dependencies=[Depends(require_api_key)])
def get_brain_status():
    return brain_status()


@app.get("/brain/memories", dependencies=[Depends(require_api_key)])
def get_brain_memories(status: str | None = None, limit: int = 100):
    if status is not None and status not in {"proposed", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Invalid memory status.")
    return list_memories(status, limit)


@app.post("/brain/memories/{memory_id}/review", dependencies=[Depends(require_owner_key)])
def post_brain_memory_review(memory_id: str, payload: BrainMemoryReview):
    try:
        result = review_memory(memory_id, payload.decision, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Proposed memory not found or already reviewed.")
    return result



@app.get("/company/workflows", dependencies=[Depends(require_api_key)])
def get_workflow_templates():
    """List available gated department workflow templates."""
    return list_templates()


@app.post("/company/workflows/{template_id}/start", status_code=201, dependencies=[Depends(require_owner_key)])
def post_start_workflow(template_id: str):
    """Create a persisted workflow; only its first task is queued."""
    try:
        return create_workflow(template_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/company/workflows/instances", dependencies=[Depends(require_api_key)])
def get_workflow_instances():
    return list_workflows()


@app.get("/company/workflows/{workflow_id}", dependencies=[Depends(require_api_key)])
def get_workflow_detail(workflow_id: str):
    result = get_workflow(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return result



class BusinessRecordRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    amount: float | None = Field(default=None, ge=0, le=1000000000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    contact: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    verified_payment: bool = False


class InvestorRequest(BaseModel):
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
def get_business_summary():
    return business_ops.business_summary()


@app.get("/business/customers", dependencies=[Depends(require_api_key)])
def get_business_customers():
    return business_ops.list_records("customer")


@app.post("/business/customers", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_customer(payload: BusinessRecordRequest):
    try:
        return business_ops.create_record("customer", payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/business/expenses", dependencies=[Depends(require_api_key)])
def get_business_expenses():
    return business_ops.list_records("expense")


@app.post("/business/expenses", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_expense(payload: BusinessRecordRequest):
    try:
        return business_ops.create_record("expense", payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/business/revenue", dependencies=[Depends(require_api_key)])
def get_business_revenue():
    return business_ops.list_records("revenue")


@app.post("/business/revenue", status_code=201, dependencies=[Depends(require_owner_key)])
def post_business_revenue(payload: BusinessRecordRequest):
    try:
        return business_ops.create_record("revenue", payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/business/investors", dependencies=[Depends(require_api_key)])
def get_business_investors():
    return business_ops.list_investors()


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
    return create_task(payload)


@app.get("/tasks", response_model=list[TaskOut], dependencies=[Depends(require_api_key)])
def get_tasks():
    return list_tasks()


@app.post("/tasks/{task_id}/execute", status_code=202, dependencies=[Depends(require_api_key)])
def execute_task(task_id: str):
    try:
        if not task_is_runnable(task_id):
            raise ValueError("This workflow step is blocked until the previous department step completes.")
        return create_run(task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/agent-runs/{run_id}/retry", status_code=202, dependencies=[Depends(require_api_key)])
def retry_agent_run(run_id: str):
    try:
        return retry_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/agent-runs", dependencies=[Depends(require_api_key)])
def get_agent_runs(task_id: str | None = None):
    return list_runs(task_id)


@app.get("/agent-runs/{run_id}", dependencies=[Depends(require_api_key)])
def get_agent_run(run_id: str):
    result = get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return result


@app.get("/agent-runs/{run_id}/events", dependencies=[Depends(require_api_key)])
def get_agent_run_events(run_id: str):
    """Return the persisted execution timeline for an owner-visible run."""
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    with connect() as db:
        rows = db.execute(
            "SELECT id, stage, message, created_at FROM agent_run_events WHERE run_id=? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]

@app.get("/agent-runs/{run_id}/steps", dependencies=[Depends(require_api_key)])
def get_agent_run_steps(run_id: str):
    """Return each collaborating agent's persisted contribution."""
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
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
def get_approvals():
    return list_approvals()


@app.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalOut,
    dependencies=[Depends(require_api_key)],
)
def post_approval_decision(approval_id: str, payload: ApprovalDecision):
    try:
        result = decide_approval(approval_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    business_ops.apply_expense_approval(approval_id, payload.decision)
    return result


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


# Social media and creative production: drafts/briefs only; no external side effects.
class SocialContentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    body: str = Field(default="", max_length=10000)
    channels: list[str] = Field(default_factory=list, max_length=8)
    content_type: str = Field(default="post", max_length=30)
    brief: dict = Field(default_factory=dict)


class SocialDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


@app.get("/social/status", dependencies=[Depends(require_api_key)])
def get_social_status():
    social_media.initialize()
    return {
        "department": "social-media-video",
        "integrations": social_media.integration_status(),
        "publishing_enabled": False,
        "paid_generation_enabled": False,
        "approval_required": True,
    }


@app.get("/social/content", dependencies=[Depends(require_api_key)])
def get_social_content(kind: str | None = Query(default=None, pattern="^(social_post|video_brief)$")):
    return social_media.list_content(kind)


@app.post("/social/content", status_code=201, dependencies=[Depends(require_owner_key)])
def post_social_content(payload: SocialContentCreate, kind: str = Query(default="social_post", pattern="^(social_post|video_brief)$")):
    try:
        return social_media.create_content(
            kind=kind, title=payload.title, body=payload.body,
            channels=payload.channels, content_type=payload.content_type,
            brief=payload.brief,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/social/content/{content_id}/request-approval", dependencies=[Depends(require_owner_key)])
def request_social_content_approval(content_id: str):
    item = social_media.get_content(content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content draft not found.")
    if item["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only draft content can be submitted for approval.")
    approval = create_approval(ApprovalCreate(
        action="Review social/video content",
        details=json.dumps({"content_id": content_id, "kind": item["kind"], "title": item["title"]}),
    ))
    updated = social_media.attach_approval(content_id, approval["id"])
    return {"content": updated, "approval": approval, "external_action": "none"}


@app.post("/social/content/{content_id}/decision", dependencies=[Depends(require_owner_key)])
def decide_social_content(content_id: str, payload: SocialDecisionRequest):
    item = social_media.get_content(content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content draft not found.")
    if item["status"] != "awaiting_approval" or not item["approval_id"]:
        raise HTTPException(status_code=409, detail="Content is not awaiting approval.")
    try:
        approval = decide_approval(item["approval_id"], ApprovalDecision(decision=payload.decision))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Linked approval request not found.")
    updated = social_media.set_decision(content_id, payload.decision)
    return {"content": updated, "approval": approval, "publishing_performed": False}


# Provider-neutral video queue. Approval only queues work; it never starts a
# provider, allocates compute, incurs cost, or publishes generated media.
class VideoJobCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    provider: str = Field(default="longcat-video", pattern="^(longcat-video|creator-clipping)$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    parameters: dict = Field(default_factory=dict)
    estimated_cost_minor: int = Field(ge=0)
    approved_budget_minor: int = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    cost_basis: str = Field(min_length=1, max_length=300)
    max_attempts: int = Field(default=3, ge=1, le=5)


# Owner-uploaded source footage is written only to an explicitly configured shared
# volume. The clipping worker must mount this same directory at CLIPPING_INPUT_DIR.
@app.post("/video/sources", status_code=201, dependencies=[Depends(require_owner_key)])
async def upload_video_source(request: Request, filename: str = Query(min_length=1, max_length=255)):
    input_dir = os.getenv("CLIPPING_INPUT_DIR", "").strip()
    if not input_dir:
        raise HTTPException(status_code=503, detail="Video source storage is not configured. Set CLIPPING_INPUT_DIR on the API and mount the same volume in the clipping worker.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm"}:
        raise HTTPException(status_code=415, detail="Only MP4, MOV and WebM source videos are supported.")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    allowed_types = {"video/mp4", "video/quicktime", "video/webm", "application/octet-stream"}
    if content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported video content type.")
    root = Path(input_dir).expanduser().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Configured video source storage is unavailable.") from exc
    token = secrets.token_hex(16)
    temporary = root / (token + ".upload")
    final_path = root / (token + suffix)
    size = 0
    prefix = bytearray()
    try:
        with temporary.open("xb") as output:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > 250 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Video upload exceeds the 250 MiB limit.")
                if len(prefix) < 32:
                    prefix.extend(chunk[:32 - len(prefix)])
                output.write(chunk)
        valid_signature = (suffix in {".mp4", ".mov"} and len(prefix) >= 12 and prefix[4:8] == b"ftyp") or (suffix == ".webm" and prefix[:4] == bytes([0x1a, 0x45, 0xdf, 0xa3]))
        if size < 16 or not valid_signature:
            raise HTTPException(status_code=422, detail="Uploaded bytes do not match the selected video format.")
        temporary.replace(final_path)
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Could not store the uploaded video.") from exc
    return {"source_path": final_path.name, "filename": Path(filename).name, "size_bytes": size, "storage": "configured_shared_volume", "worker_provider": "creator-clipping"}


class VideoJobDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    approval_note: str = Field(default="", max_length=1000)


@app.get("/video/status", dependencies=[Depends(require_api_key)])
def get_video_status():
    video_jobs.initialize()
    return {
        "queue": "sqlite-durable",
        **video_jobs.worker_status(),
        "publishing_enabled": False,
    }


@app.post("/video/jobs", status_code=201, dependencies=[Depends(require_owner_key)])
def post_video_job(payload: VideoJobCreate):
    try:
        return video_jobs.create_job(
            prompt=payload.prompt, provider=payload.provider,
            idempotency_key=payload.idempotency_key, parameters=payload.parameters,
            estimated_cost_minor=payload.estimated_cost_minor,
            approved_budget_minor=payload.approved_budget_minor,
            currency=payload.currency, cost_basis=payload.cost_basis,
            max_attempts=payload.max_attempts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/video/jobs", dependencies=[Depends(require_api_key)])
def get_video_jobs(status: str | None = Query(default=None, pattern="^(awaiting_approval|queued|running|succeeded|failed|rejected|cancelled)$")):
    return video_jobs.list_jobs(status)


@app.get("/video/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_video_job(job_id: str):
    item = video_jobs.get_job(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Video job not found.")
    return item


@app.post("/video/jobs/{job_id}/decision", dependencies=[Depends(require_owner_key)])
def decide_video_job(job_id: str, payload: VideoJobDecision):
    try:
        item = video_jobs.decide_job(
            job_id, payload.decision, approval_note=payload.approval_note
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Video job not found.")
    return {"job": item, "generation_started": False, "publishing_performed": False}



class VideoWorkerClaim(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    lease_seconds: int = Field(default=120, ge=30, le=900)
    provider: str = Field(default="longcat-video", pattern="^(longcat-video|creator-clipping)$")


class VideoWorkerHeartbeat(BaseModel):
    progress: float | None = Field(default=None, ge=0, le=100)
    message: str = Field(default="", max_length=240)


class VideoWorkerComplete(BaseModel):
    result_uri: str = Field(min_length=9, max_length=2048)
    metadata: dict = Field(default_factory=dict)


class VideoWorkerFailure(BaseModel):
    error: str = Field(min_length=1, max_length=2000)
    retryable: bool = True


def require_video_worker(x_video_worker_token: str | None = Header(default=None, alias="X-Video-Worker-Token")):
    expected = os.getenv("VIDEO_WORKER_TOKEN", "").strip()
    if not expected or not x_video_worker_token or not hmac.compare_digest(expected, x_video_worker_token.strip()):
        raise HTTPException(status_code=401, detail="Valid video worker credential required.")


@app.get("/video/jobs/{job_id}/events", dependencies=[Depends(require_api_key)])
def get_video_job_events(job_id: str):
    if video_jobs.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Video job not found.")
    return video_jobs.list_events(job_id)


@app.post("/video/jobs/{job_id}/cancel", dependencies=[Depends(require_owner_key)])
def post_video_job_cancel(job_id: str):
    try:
        item = video_jobs.cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Video job not found.")
    return {"job": item, "cancellation": "requested" if item["status"] == "running" else item["status"]}


@app.post("/video/worker/claim", dependencies=[Depends(require_video_worker)])
def post_video_worker_claim(payload: VideoWorkerClaim):
    try:
        return video_jobs.claim_job(payload.worker_id, payload.lease_seconds, provider=payload.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/video/worker/jobs/{job_id}/heartbeat", dependencies=[Depends(require_video_worker)])
def post_video_worker_heartbeat(job_id: str, payload: VideoWorkerHeartbeat, x_job_lease: str | None = Header(default=None, alias="X-Job-Lease")):
    try:
        return video_jobs.heartbeat(job_id, x_job_lease, progress=payload.progress, message=payload.message)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/video/worker/jobs/{job_id}/complete", dependencies=[Depends(require_video_worker)])
def post_video_worker_complete(job_id: str, payload: VideoWorkerComplete, x_job_lease: str | None = Header(default=None, alias="X-Job-Lease")):
    try:
        return video_jobs.complete_job(job_id, x_job_lease, result_uri=payload.result_uri, metadata=payload.metadata)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/video/worker/jobs/{job_id}/fail", dependencies=[Depends(require_video_worker)])
def post_video_worker_fail(job_id: str, payload: VideoWorkerFailure, x_job_lease: str | None = Header(default=None, alias="X-Job-Lease")):
    try:
        return video_jobs.fail_job(job_id, x_job_lease, error=payload.error, retryable=payload.retryable)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



@app.put("/video/worker/jobs/{job_id}/artifact", dependencies=[Depends(require_video_worker)])
async def put_video_worker_artifact(job_id: str, request: Request, x_job_lease: str | None = Header(default=None, alias="X-Job-Lease")):
    import uuid as _uuid
    item = video_jobs.get_job(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Video job not found.")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "video/mp4":
        raise HTTPException(status_code=415, detail="Only video/mp4 artifacts are accepted.")
    public_base = os.getenv("PUBLIC_API_BASE_URL", "").rstrip("/")
    if not public_base.startswith("https://"):
        raise HTTPException(status_code=503, detail="Set PUBLIC_API_BASE_URL to the public HTTPS API origin before accepting artifacts.")
    try:
        lease_state = video_jobs.heartbeat(job_id, x_job_lease, progress=95, message="Uploading generated MP4")
        if lease_state.get("cancel_requested"):
            raise HTTPException(status_code=409, detail="Cancellation was requested.")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    directory = Path(os.getenv("VIDEO_ARTIFACT_DIR", "./video_artifacts")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    job_uuid = _uuid.UUID(job_id)
    destination = directory / f"{job_uuid}.mp4"
    temporary = directory / f".{job_uuid}.{_uuid.uuid4().hex}.tmp"
    size = 0
    prefix = bytearray()
    try:
        with temporary.open("wb") as output:
            last_lease_refresh = time.monotonic()
            async for chunk in request.stream():
                size += len(chunk)
                if size > 300 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Artifact exceeds 300 MB limit.")
                if len(prefix) < 12:
                    prefix.extend(chunk[:12 - len(prefix)])
                output.write(chunk)
                # Keep the lease alive during slow uploads and observe owner cancellation.
                if time.monotonic() - last_lease_refresh >= 10:
                    try:
                        lease_state = video_jobs.heartbeat(
                            job_id, x_job_lease, progress=95, message="Uploading generated MP4"
                        )
                    except (LookupError, PermissionError) as exc:
                        raise HTTPException(status_code=409, detail=str(exc)) from exc
                    if lease_state.get("cancel_requested"):
                        raise HTTPException(status_code=409, detail="Cancellation was requested.")
                    last_lease_refresh = time.monotonic()
        if size < 12 or bytes(prefix[4:8]) != b"ftyp":
            raise HTTPException(status_code=422, detail="Uploaded bytes are not a valid MP4 container.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    uri = f"{public_base}/video/artifacts/{job_id}"
    try:
        completed = video_jobs.complete_job(
            job_id, x_job_lease, result_uri=uri,
            metadata={"content_type":"video/mp4","size_bytes":size,"storage":"api-artifact-volume"},
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return completed


@app.get("/video/artifacts/{job_id}", dependencies=[Depends(require_owner_key)])
def get_video_artifact(job_id: str):
    item = video_jobs.get_job(job_id)
    if item is None or item["status"] != "succeeded":
        raise HTTPException(status_code=404, detail="Video artifact not found.")
    directory = Path(os.getenv("VIDEO_ARTIFACT_DIR", "./video_artifacts")).resolve()
    path = directory / f"{job_id}.mp4"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact storage is unavailable; verify the persistent volume.")
    return FileResponse(path, media_type="video/mp4", filename=f"opencompany-{job_id}.mp4")
