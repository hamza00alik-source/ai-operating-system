"""FastAPI application."""
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ai_os.audit import append_event, list_events, verify_chain
from ai_os.auth import authenticate_request
from ai_os.db import initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision, ApprovalOut, TaskCreate, TaskOut
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks
from ai_os.agent_schemas import AgentOut, AgentProfileOut, PlanCreate, PlanOut
from ai_os.registry import get_agent, list_agents, load_agent_profile
from ai_os.orchestrator import build_plan
from ai_os.manual_schemas import WorkPacketCreate, WorkPacketOut, RuntimeStatus
from ai_os.work_packets import build_work_packet
from ai_os.queue_schemas import JobCreate, JobOut, WorkerRunOut
from ai_os.queue import enqueue_job, list_jobs
from ai_os.worker import run_once
from ai_os.governance import evaluate_action
from ai_os.governance_schemas import GovernanceEvaluateIn, GovernanceEvaluateOut
from ai_os.runbooks import get_runbook, list_runbooks
from ai_os.execution_schemas import CompanyRunCreate, CompanyRunOut, StepReportCreate, StepOut
from ai_os.execution import create_company_run, list_company_runs, get_company_run, dispatch_ready_step, submit_step_report

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield

app = FastAPI(title="AI Operating System", version="0.6.0", description="Human-supervised AI company workflow foundation.", lifespan=lifespan)

@app.middleware("http")
async def owner_auth_and_audit(request: Request, call_next):
    request_id = str(uuid4())
    auth_response = await authenticate_request(request)
    if auth_response is not None:
        auth_response.headers["X-Request-ID"] = request_id
        try:
            append_event(
                getattr(request.state, "actor", "anonymous"),
                "request_denied", "http_request", request.url.path,
                {"method": request.method, "status": auth_response.status_code, "request_id": request_id},
            )
        except Exception:
            logger.exception("Could not write denied-request audit event")
        return auth_response

    try:
        response = await call_next(request)
    except Exception:
        try:
            append_event(
                getattr(request.state, "actor", "unknown"),
                "request_failed", "http_request", request.url.path,
                {"method": request.method, "status": 500, "request_id": request_id},
            )
        except Exception:
            logger.exception("Could not write failed-request audit event")
        raise

    response.headers["X-Request-ID"] = request_id
    if request.url.path != "/health":
        try:
            append_event(
                getattr(request.state, "actor", "unknown"),
                "request", "http_request", request.url.path,
                {"method": request.method, "status": response.status_code, "request_id": request_id},
            )
        except Exception:
            logger.exception("Audit write failed after request processing")
            return JSONResponse(
                status_code=503,
                headers={"X-Request-ID": request_id},
                content={"detail": "Audit storage failed after request processing. Inspect system state before retrying."},
            )
    return response

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

@app.get("/audit")
def get_audit_events(limit: int = Query(default=100, ge=1, le=500)):
    return {"events": list_events(limit)}

@app.get("/audit/verify")
def get_audit_verification():
    return verify_chain()

@app.get("/agents", response_model=list[AgentOut])
def get_agents():
    return [agent.__dict__ for agent in list_agents()]

@app.get("/runbooks")
def get_runbooks():
    return {"runbooks": list_runbooks()}

@app.get("/runbooks/{slug}")
def get_runbook_detail(slug: str):
    runbook = get_runbook(slug)
    if runbook is None:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return runbook

@app.get("/agents/{agent_id}/profile", response_model=AgentProfileOut)
def get_agent_profile(agent_id: str):
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        profile = load_agent_profile(agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Agency Agents submodule is not initialized") from exc
    return {
        "id": agent.id,
        "name": agent.name,
        "department": agent.department,
        "profile_path": agent.profile_path,
        "profile_markdown": profile or agent.description,
    }

@app.post("/governance/evaluate", response_model=GovernanceEvaluateOut)
def post_governance_evaluation(payload: GovernanceEvaluateIn):
    """Preview central CEO policy; this endpoint does not execute the action."""
    return evaluate_action(payload.agent_id, payload.action)

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

@app.post("/company-runs", response_model=CompanyRunOut, status_code=201)
def post_company_run(payload: CompanyRunCreate):
    try:
        return create_company_run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.get("/company-runs", response_model=list[CompanyRunOut])
def get_company_runs(limit: int = Query(default=100, ge=1, le=500)):
    return list_company_runs(limit)

@app.get("/company-runs/{run_id}", response_model=CompanyRunOut)
def get_company_run_detail(run_id: str):
    run = get_company_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Company run not found")
    return run

@app.post("/company-runs/{run_id}/steps/{step_key}/dispatch", response_model=StepOut)
def post_company_step_dispatch(run_id: str, step_key: str):
    try:
        return dispatch_ready_step(run_id, step_key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@app.post("/company-runs/{run_id}/steps/{step_key}/report", response_model=StepOut)
def post_company_step_report(run_id: str, step_key: str, payload: StepReportCreate):
    try:
        return submit_step_report(run_id, step_key, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
