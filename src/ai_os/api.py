"""FastAPI application."""
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

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
from ai_os.agent_runtime import schedule_ready_steps
from ai_os.governance import evaluate_action
from ai_os.governance_schemas import GovernanceEvaluateIn, GovernanceEvaluateOut
from ai_os.runbooks import get_runbook, list_runbooks
from ai_os.execution_schemas import CompanyRunCreate, CompanyRunOut, StepReportCreate, StepOut
from ai_os.execution import create_company_run, list_company_runs, get_company_run, dispatch_ready_step, submit_step_report
from ai_os.ceo_schemas import CEOObjectiveCreate, CEOPlanOut
from ai_os.ceo_brain import create_ceo_plan, get_ceo_plan
from ai_os.model_adapter import get_model_status
from ai_os.ceo_review import review_company_run
from ai_os.identity import AgentIdentityError, consume_agent_token
from ai_os.knowledge_schemas import KnowledgeCreate, KnowledgeReview
from ai_os.evaluation import list_evaluations, evaluation_summary, evaluation_trends
from ai_os.knowledge import (create_knowledge_item, get_knowledge_item,
                            list_knowledge_items, review_knowledge_item)
from ai_os.improvement import (draft_improvement_proposals, list_improvement_proposals,
                               review_improvement_proposal)
from ai_os.improvement_testing import run_proposal_regression_tests, list_proposal_test_runs

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

@app.get("/dashboard", response_class=HTMLResponse)
def owner_dashboard():
    """Serve the owner UI shell; all data APIs remain protected by owner authentication."""
    dashboard_path = Path(__file__).with_name("dashboard.html")
    return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))

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
        "model_execution_enabled": get_model_status()["enabled"],
        "model_provider_configured": get_model_status()["configured"],
    }

@app.get("/audit")
def get_audit_events(limit: int = Query(default=100, ge=1, le=500)):
    return {"events": list_events(limit)}

@app.get("/evaluations")
def get_agent_evaluations(
    limit: int = Query(default=100, ge=1, le=500),
    agent_id: str | None = Query(default=None, max_length=120),
    run_id: str | None = Query(default=None, max_length=120),
):
    return {
        "summary": evaluation_summary(agent_id=agent_id),
        "evaluations": list_evaluations(limit=limit, agent_id=agent_id, run_id=run_id),
    }

@app.get("/evaluations/trends")
def get_agent_evaluation_trends(
    agent_id: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=2, le=100),
):
    return evaluation_trends(agent_id=agent_id, limit=limit)


@app.post("/ceo/improvement-proposals/draft", status_code=201)
def post_ceo_improvement_proposals_draft(request: Request, limit: int = Query(default=100, ge=1, le=500)):
    """CEO rule-based proposal generation from repeated failed evaluation checks; no live changes."""
    proposals = draft_improvement_proposals(limit=limit)
    for proposal in proposals:
        append_event(
            getattr(request.state, "actor", "unknown"),
            "improvement_proposal_drafted", "improvement_proposal", proposal["id"],
            {"agent_id": proposal["agent_id"], "title": proposal["title"],
             "evidence_count": len(proposal["evidence"])},
        )
    return {"created": len(proposals), "proposals": proposals,
            "limitations": ["Rule-based suggestions only; no model/prompt/policy is changed.",
                            "Proposals require owner review and a separate regression-testing stage."]}


@app.get("/improvement-proposals")
def get_improvement_proposals(
    status: str | None = Query(default=None, pattern=r"^(candidate|approved_for_testing|rejected)$"),
    limit: int = Query(default=100, ge=1, le=500),
):
    return list_improvement_proposals(status=status, limit=limit)


@app.post("/improvement-proposals/{proposal_id}/review")
def post_improvement_proposal_review(proposal_id: str, payload: dict, request: Request):
    decision = payload.get("decision")
    note = payload.get("note", "")
    if decision not in {"approved_for_testing", "rejected"} or not isinstance(note, str):
        raise HTTPException(status_code=422, detail="Provide decision approved_for_testing or rejected and an optional note.")
    actor = getattr(request.state, "actor", "unknown")
    try:
        proposal = review_improvement_proposal(
            proposal_id, decision=decision, actor=actor, note=note
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if proposal is None:
        raise HTTPException(status_code=404, detail="Improvement proposal not found")
    append_event(actor, "improvement_proposal_reviewed", "improvement_proposal",
                 proposal_id, {"decision": decision})
    return proposal


@app.post("/improvement-proposals/{proposal_id}/test", status_code=201)
def post_improvement_proposal_test(proposal_id: str, request: Request):
    """Run static contract checks for an owner-approved candidate; never activate it."""
    try:
        result = run_proposal_regression_tests(proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Improvement proposal not found")
    actor = getattr(request.state, "actor", "unknown")
    append_event(actor, "improvement_proposal_tested", "improvement_proposal",
                 proposal_id, {"test_run_id": result["id"], "passed": result["passed"]})
    return result


@app.get("/improvement-proposals/{proposal_id}/tests")
def get_improvement_proposal_tests(
    proposal_id: str, limit: int = Query(default=20, ge=1, le=100)
):
    return list_proposal_test_runs(proposal_id, limit=limit)


@app.get("/audit/verify")
def get_audit_verification():
    return verify_chain()



@app.post("/knowledge", status_code=201)
def post_knowledge_candidate(payload: KnowledgeCreate, request: Request):
    """Store source-attributed research as an unreviewed candidate, never as trusted fact."""
    item = create_knowledge_item(payload, actor=getattr(request.state, "actor", "unknown"))
    append_event(
        getattr(request.state, "actor", "unknown"),
        "knowledge_candidate_created", "knowledge_item", item["id"],
        {"category": item["category"], "source_url": item["source_url"]},
    )
    return item


@app.get("/knowledge")
def get_knowledge_candidates(
    status: str | None = Query(default=None, pattern=r"^(candidate|accepted|rejected)$"),
    category: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
):
    return list_knowledge_items(limit=limit, status=status, category=category)


@app.get("/knowledge/{item_id}")
def get_knowledge_detail(item_id: str):
    item = get_knowledge_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return item


@app.post("/knowledge/{item_id}/review")
def post_knowledge_review(item_id: str, payload: KnowledgeReview, request: Request):
    actor = getattr(request.state, "actor", "unknown")
    try:
        item = review_knowledge_item(item_id, payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    append_event(
        actor, "knowledge_candidate_reviewed", "knowledge_item", item_id,
        {"decision": payload.decision},
    )
    return item

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

@app.post("/ceo/plan", response_model=CEOPlanOut, status_code=201)
def post_ceo_plan(payload: CEOObjectiveCreate):
    """CEO decomposes an objective into a persistent, reviewable company run."""
    try:
        return create_ceo_plan(payload)
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.get("/models/status")
def get_model_runtime_status():
    return get_model_status()

@app.post("/ceo/review/{run_id}")
def post_ceo_review(run_id: str):
    try:
        return review_company_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.get("/ceo/plans/{run_id}", response_model=CEOPlanOut)
def get_ceo_plan_detail(run_id: str):
    plan = get_ceo_plan(run_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="CEO plan not found")
    return plan

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
def post_company_step_report(
    run_id: str,
    step_key: str,
    payload: StepReportCreate,
    agent_token: str | None = Header(default=None, alias="X-AI-Agent-Token"),
):
    """Accept a step report only from the specialist assigned to this run step."""
    if not agent_token:
        raise HTTPException(status_code=401, detail="A signed internal agent token is required.")
    run = get_company_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Company run not found")
    step = next((item for item in run["steps"] if item["step_key"] == step_key), None)
    if step is None:
        raise HTTPException(status_code=404, detail="Company run step not found")
    if step["status"] != "assigned":
        raise HTTPException(status_code=409, detail="A report can be submitted only for an assigned step.")
    try:
        principal = consume_agent_token(
            agent_token,
            expected_agent_id=step["agent_id"],
            expected_run_id=run_id,
            required_capability="step.report",
        )
    except AgentIdentityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        result = submit_step_report(run_id, step_key, payload)
        append_event(
            f"agent:{principal.agent_id}",
            "company_step_reported",
            "company_run_step",
            f"{run_id}:{step_key}",
            {"run_id": run_id, "step_key": step_key, "status": payload.status},
        )
        return result
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
    elif payload.job_type == "execute_company_step":
        if set(payload.payload) != {"run_id", "step_key"} or not all(
            isinstance(payload.payload.get(key), str) and payload.payload[key].strip()
            for key in ("run_id", "step_key")
        ):
            raise HTTPException(status_code=422, detail="payload requires only run_id and step_key")
    return enqueue_job(payload)

@app.get("/jobs", response_model=list[JobOut])
def get_jobs(limit: int = Query(default=100, ge=1, le=500)):
    return list_jobs(limit)

@app.post("/worker/run-once", response_model=WorkerRunOut)
def post_worker_run_once():
    schedule_ready_steps()
    return run_once()

@app.post("/tasks", response_model=TaskOut, status_code=201)
def post_task(payload: TaskCreate):
    return create_task(payload)

@app.get("/tasks", response_model=list[TaskOut])
def get_tasks():
    return list_tasks()

@app.post("/approvals", response_model=ApprovalOut, status_code=201)
def post_approval(payload: ApprovalCreate, request: Request):
    """Accept approval requests only from a trusted in-process CEO runtime.

    The current runtime has no authenticated agent identity, so owner-token
    callers are deliberately not treated as the CEO. Keep this route closed
    until a server-verified CEO principal is introduced.
    """
    if getattr(request.state, "actor", None) != "ceo":
        raise HTTPException(
            status_code=403,
            detail="Approval requests are disabled until a trusted CEO runtime identity is available.",
        )
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
