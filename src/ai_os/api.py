"""FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from ai_os.auth import require_api_key
from ai_os.config import get_settings
from ai_os.db import initialize_database
from ai_os.model_adapter import ModelAdapterError, chat_completion, get_model_status\nfrom ai_os.mcp_registry import MCPRegistryError, list_mcp_servers
from ai_os.provider_catalog import list_providers
from ai_os.schemas import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalOut,
    ModelTestRequest,
    TaskCreate,
    TaskOut,
)
from ai_os.service import (
    create_approval,
    create_task,
    decide_approval,
    list_approvals,
    list_tasks,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.environment != "development" and not settings.api_key:
        raise RuntimeError("AI_OS_API_KEY must be set outside development.")
    initialize_database()
    yield


app = FastAPI(
    title="AI Operating System",
    version="0.1.0",
    description="Human-supervised AI company workflow foundation.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-operating-system"}


@app.post("/tasks", response_model=TaskOut, status_code=201, dependencies=[Depends(require_api_key)])
def post_task(payload: TaskCreate):
    return create_task(payload)


@app.get("/tasks", response_model=list[TaskOut], dependencies=[Depends(require_api_key)])
def get_tasks():
    return list_tasks()


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


@app.get("/models/status", dependencies=[Depends(require_api_key)])
def models_status():
    """Return safe provider configuration status without exposing credentials."""
    return get_model_status()


@app.get("/models/providers", dependencies=[Depends(require_api_key)])
def models_providers():
    """List provider discovery metadata; this does not contact providers."""
    return list_providers()


@app.get("/mcp/servers", dependencies=[Depends(require_api_key)])\ndef mcp_servers():\n    """List sanitized MCP connection manifests; does not connect or execute tools."""\n    try:\n        return list_mcp_servers()\n    except MCPRegistryError as exc:\n        raise HTTPException(status_code=422, detail=str(exc)) from exc\n\n\n@app.post("/models/test", dependencies=[Depends(require_api_key)])
def test_model(payload: ModelTestRequest):
    """Make one explicitly enabled model request; never auto-fallback to another provider."""
    try:
        return chat_completion(payload.prompt)
    except ModelAdapterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
