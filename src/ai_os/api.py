"""FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from ai_os.db import initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision, ApprovalOut, TaskCreate, TaskOut
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks
from ai_os.agent_schemas import AgentOut, PlanCreate, PlanOut
from ai_os.registry import list_agents
from ai_os.orchestrator import build_plan

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield

app = FastAPI(title="AI Operating System", version="0.2.0", description="Human-supervised AI company workflow foundation.", lifespan=lifespan)

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-operating-system"}

@app.get("/agents", response_model=list[AgentOut])
def get_agents():
    return [agent.__dict__ for agent in list_agents()]

@app.post("/plans", response_model=PlanOut, status_code=201)
def post_plan(payload: PlanCreate):
    try:
        return build_plan(payload.title, payload.description, payload.department)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.post("/tasks", response_model=TaskOut, status_code=201)
def post_task(payload: TaskCreate):
    return create_task(payload)

@app.get("/tasks", response_model=list[TaskOut])
def get_tasks():
    return list_tasks()

@app.post("/approvals", response_model=ApprovalOut, status_code=201)
def post_approval(payload: ApprovalCreate):
    try:
        return create_approval(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.get("/approvals", response_model=list[ApprovalOut])
def get_approvals():
    return list_approvals()

@app.post("/approvals/{approval_id}/decision", response_model=ApprovalOut)
def post_approval_decision(approval_id: str, payload: ApprovalDecision):
    try:
        result = decide_approval(approval_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return result
