"""FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query

from ai_os.auth import require_api_key
from ai_os.config import get_settings
from ai_os.coordination import (
    claim_next_task,
    list_agents,
    list_audit_events,
    register_agent,
    search_memory,
    write_memory,
)
from ai_os.db import initialize_database
from ai_os.schemas import (
    AgentOut,
    AgentRegister,
    ApprovalCreate,
    ApprovalDecision,
    ApprovalOut,
    AuditEventOut,
    MemoryCreate,
    MemoryOut,
    TaskCreate,
    TaskOut,
)
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.environment != "development" and not settings.api_key:
        raise RuntimeError("AI_OS_API_KEY must be set outside development.")
    initialize_database()
    yield


app = FastAPI(
    title="AI Operating System",
    version="0.2.0",
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


@app.post(
    "/agents/register",
    response_model=AgentOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def post_agent(payload: AgentRegister):
    return register_agent(payload.agent_id, payload.name, payload.role)


@app.get(
    "/agents",
    response_model=list[AgentOut],
    dependencies=[Depends(require_api_key)],
)
def get_agents():
    return list_agents()


@app.post(
    "/agents/{agent_id}/claim",
    response_model=TaskOut | None,
    dependencies=[Depends(require_api_key)],
)
def post_claim_task(agent_id: str):
    try:
        return claim_next_task(agent_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/memory",
    response_model=MemoryOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def post_memory(payload: MemoryCreate):
    return write_memory(payload.key, payload.content, payload.source, payload.created_by)


@app.get(
    "/memory",
    response_model=list[MemoryOut],
    dependencies=[Depends(require_api_key)],
)
def get_memory(q: str = "", limit: int = Query(default=50, ge=1, le=100)):
    return search_memory(q, limit)


@app.get(
    "/audit",
    response_model=list[AuditEventOut],
    dependencies=[Depends(require_api_key)],
)
def get_audit(limit: int = Query(default=100, ge=1, le=200)):
    return list_audit_events(limit)
