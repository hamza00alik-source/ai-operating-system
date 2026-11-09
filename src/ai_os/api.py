"""FastAPI application."""
from contextlib import asynccontextmanager
import logging
import threading
import unicodedata
import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
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
from ai_os.research_sources import capture_source, list_sources
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
    base_url: str | None = Field(default=None, max_length=500)


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
        save_provider_credential(provider_id, payload.api_key, payload.model, payload.confirm_free_only, payload.base_url)
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
            "workflow_status": "catalogue-only",
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
        return create_run(task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
