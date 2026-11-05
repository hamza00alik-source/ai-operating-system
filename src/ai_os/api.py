"""FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from ai_os.db import initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision, ApprovalOut, TaskCreate, TaskOut
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks
from ai_os.agent_schemas import AgentOut, PlanCreate, PlanOut
from ai_os.registry import list_agents
from ai_os.orchestrator import build_plan
from ai_os.manual_schemas import WorkPacketCreate, WorkPacketOut, RuntimeStatus
from ai_os.work_packets import build_work_packet
from ai_os.queue_schemas import JobCreate, JobOut, WorkerRunOut
from ai_os.queue import enqueue_job, list_jobs
from ai_os.worker import run_once

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield

app = FastAPI(title="AI Operating System", version="0.4.0", description="Human-supervised AI company workflow foundation.", lifespan=lifespan)

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-operating-system"}

@app.get("/runtime", response_model=RuntimeStatus)
def get_runtime_status():
    return {
        "mode": "manual_free_chat",
        "agent_profiles_available": True,
        "manual_free_chat_available": True,
        "model_api_configured": False,
        "paid_api_calls_enabled": False,
        "autonomous_execution_enabled": False,
        "external_actions_enabled": False,
    }

@app.get("/agents", response_model=list[AgentOut])
def get_agents():
    return [agent.__dict__ for agent in list_agents()]

@app.post("/plans", response_model=PlanOut, status_code=201)
def post_plan(payload: PlanCreate):
    try:
        return build_plan(payload.title, payload.description, payload.department)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.post("/work-packets", response_model=WorkPacketOut, status_code=201)
def post_work_packet(payload: WorkPacketCreate):
    try:
        return build_work_packet(payload.agent_id, payload.task, payload.context)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.post("/jobs", response_model=JobOut, status_code=201)
def post_job(payload: JobCreate):
    if payload.job_type == "build_work_packet":
        required = {"agent_id", "task"}
        if not required.issubset(payload.payload):
            raise HTTPException(status_code=422, detail="payload requires agent_id and task")
        if not isinstance(payload.payload.get("agent_id"), str) or not isinstance(payload.payload.get("task"), str):
            raise HTTPException(status_code=422, detail="agent_id and task must be strings")
        if not payload.payload["task"].strip():
            raise HTTPException(status_code=422, detail="task must not be blank")
        if not isinstance(payload.payload.get("context", ""), str):
            raise HTTPException(status_code=422, detail="context must be a string")
    return enqueue_job(payload)

@app.get("/jobs", response_model=list[JobOut])
def get_jobs(limit: int = Query(default=100, ge=1, le=500)):
    return list_jobs(limit)

@app.post("/worker/run-once", response_model=WorkerRunOut)
def post_worker_run_once():
    return run_once()

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
