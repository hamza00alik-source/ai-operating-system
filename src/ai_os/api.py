"""FastAPI application."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from ai_os.agent_runtime import agent_graph_enabled, get_task_memory, list_task_steps
from ai_os.auth import Principal, require_operator, require_owner, require_reader, require_task_writer
from ai_os.config import get_settings
from ai_os.db import connect, initialize_database
from ai_os.embedded_worker import start_embedded_worker
from ai_os.mcp_registry import create_mcp_server, list_mcp_servers, set_mcp_server_enabled
from ai_os.mcp_client import probe_mcp_server
from ai_os.model_adapter import generate_text, get_model_status
from ai_os.heartbeat import get_worker_status
from ai_os.schemas import (
    ApprovalCreate, ApprovalDecision, ApprovalOut, AuditEventOut,
    MCPServerCreate, MCPServerOut, TaskCreate, TaskOut,
)
from ai_os.service import (
    create_approval, create_task, decide_approval, list_approvals,
    list_audit_events, list_tasks,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.environment != "development" and not (settings.api_key or settings.api_keys):
        raise RuntimeError("Set AI_OS_API_KEY or AI_OS_API_KEYS outside development.")
    initialize_database()
    stop_worker = start_embedded_worker()
    try:
        yield
    finally:
        if stop_worker is not None:
            stop_worker()


app = FastAPI(
    title="AI Operating System",
    version="0.1.0",
    description="Human-supervised AI company workflow foundation.",
    lifespan=lifespan,
)


@app.get("/owner/verification", include_in_schema=False)
def owner_verification_dashboard():
    """Serve the visual owner console; all operational data remains API-key protected."""
    page = Path(__file__).parent / "static" / "owner.html"
    return FileResponse(page, media_type="text/html", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-operating-system"}


@app.get("/runtime/status", dependencies=[Depends(require_reader)])
def runtime_status() -> dict:
    """Expose safe runtime configuration only; never return endpoint URLs or secrets."""
    return {"model": get_model_status(), "agent_graph_enabled": agent_graph_enabled(),
            "worker_heartbeat_available": True, "worker": get_worker_status()}


@app.post("/runtime/model-test", dependencies=[Depends(require_owner)])
def runtime_model_test() -> dict:
    """Send one fixed, harmless connectivity prompt only after an owner clicks Test."""
    status = get_model_status()
    if not status["enabled"] or not status["configured"]:
        raise HTTPException(
            status_code=409,
            detail="Model execution is disabled or the endpoint/model is not configured.",
        )
    try:
        output = generate_text(
            "AIOS connectivity check. Reply with exactly: AIOS_MODEL_CONNECTION_OK",
            timeout=20,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "provider": status["provider"],
        "model": status["model"],
        "output": output[:500],
    }


@app.post("/tasks", response_model=TaskOut, status_code=201)
def post_task(payload: TaskCreate, principal: Principal = Depends(require_task_writer)):
    return create_task(payload, actor_id=principal.principal_id)


@app.get("/tasks", response_model=list[TaskOut], dependencies=[Depends(require_reader)])
def get_tasks():
    return list_tasks()


@app.post("/approvals", response_model=ApprovalOut, status_code=201)
def post_approval(payload: ApprovalCreate, principal: Principal = Depends(require_operator)):
    try:
        # The authenticated principal, not a caller-supplied actor_id, is authoritative.
        payload = payload.model_copy(update={"actor_id": principal.principal_id})
        return create_approval(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Approval action payload must be valid JSON data.") from exc


@app.get("/approvals", response_model=list[ApprovalOut], dependencies=[Depends(require_reader)])
def get_approvals():
    return list_approvals()


@app.post("/approvals/{approval_id}/decision", response_model=ApprovalOut)
def post_approval_decision(approval_id: str, payload: ApprovalDecision,
                           principal: Principal = Depends(require_owner)):
    try:
        result = decide_approval(approval_id, payload, actor_id=principal.principal_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return result


@app.get("/audit/events", response_model=list[AuditEventOut], dependencies=[Depends(require_reader)])
def get_audit_events(limit: int = Query(default=100, ge=1, le=500),
                     before_id: int | None = Query(default=None, ge=1)):
    """Return newest audit events first; use before_id for stable older-page retrieval."""
    return list_audit_events(limit=limit, before_id=before_id)


@app.get("/tasks/{task_id}/memory", dependencies=[Depends(require_reader)])
def get_task_memory_endpoint(task_id: str):
    with connect() as db:
        exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Task not found")
    return get_task_memory(task_id)


@app.get("/tasks/{task_id}/steps", dependencies=[Depends(require_reader)])
def get_task_steps_endpoint(task_id: str):
    with connect() as db:
        exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Task not found")
    return list_task_steps(task_id)


@app.post("/mcp/servers", response_model=MCPServerOut, status_code=201)
def post_mcp_server(payload: MCPServerCreate, principal: Principal = Depends(require_owner)):
    try:
        return create_mcp_server(payload, actor_id=principal.principal_id)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already registered" in str(exc) else 422, detail=str(exc)) from exc


@app.get("/mcp/servers", response_model=list[MCPServerOut], dependencies=[Depends(require_reader)])
def get_mcp_servers():
    return list_mcp_servers()


@app.post("/mcp/servers/{server_id}/test", dependencies=[Depends(require_owner)])
def post_mcp_server_test(server_id: str):
    """Owner-triggered, read-only MCP handshake and tools/list discovery."""
    try:
        return probe_mcp_server(server_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/mcp/servers/{server_id}/enabled", response_model=MCPServerOut)
def post_mcp_server_enabled(server_id: str, enabled: bool, principal: Principal = Depends(require_owner)):
    result = set_mcp_server_enabled(server_id, enabled, actor_id=principal.principal_id)
    if result is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return result
