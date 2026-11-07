"""FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from ai_os.auth import require_api_key
from ai_os.config import get_settings
from ai_os.db import initialize_database
from ai_os.schemas import (
    AgentCreate, AgentOut, ApprovalCreate, ApprovalDecision, ApprovalOut,
    TaskCreate, TaskOut,
)
from ai_os.service import (
    assign_task, create_approval, create_task, decide_approval, list_agents,
    list_approvals, list_tasks, register_agent,
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


@app.get("/agents", response_model=list[AgentOut], dependencies=[Depends(require_api_key)])
def get_agents():
    return list_agents()


@app.post("/agents", response_model=AgentOut, status_code=201, dependencies=[Depends(require_api_key)])
def post_agent(payload: AgentCreate):
    try:
        return register_agent(payload)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Agent name already exists") from exc
        raise


@app.post("/tasks", response_model=TaskOut, status_code=201, dependencies=[Depends(require_api_key)])
def post_task(payload: TaskCreate):
    return create_task(payload)


@app.get("/tasks", response_model=list[TaskOut], dependencies=[Depends(require_api_key)])
def get_tasks():
    return list_tasks()


@app.post("/tasks/{task_id}/assign/{agent_id}", response_model=TaskOut, dependencies=[Depends(require_api_key)])
def post_task_assignment(task_id: str, agent_id: str):
    try:
        result = assign_task(task_id, agent_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.post("/approvals", response_model=ApprovalOut, status_code=201, dependencies=[Depends(require_api_key)])
def post_approval(payload: ApprovalCreate):
    try:
        return create_approval(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/approvals", response_model=list[ApprovalOut], dependencies=[Depends(require_api_key)])
def get_approvals():
    return list_approvals()


@app.post("/approvals/{approval_id}/decision", response_model=ApprovalOut, dependencies=[Depends(require_api_key)])
def post_approval_decision(approval_id: str, payload: ApprovalDecision):
    try:
        result = decide_approval(approval_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return result
