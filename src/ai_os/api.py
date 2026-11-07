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
from ai_os.approval_schemas import CEOApprovalRequestCreate, OwnerApprovalDecision
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks
from ai_os.approvals import (ApprovalSecurityError, create_owner_approval_request,
                             decide_owner_approval, list_owner_approval_requests)
from ai_os.action_gateway import ActionGatewayError, execute_approved_action
from ai_os.wordpress_actions import register_wordpress_draft_adapter
from ai_os.wordpress import WordPressNotConfigured, WordPressReadError, WordPressReadOnlyClient
from ai_os.woocommerce import WooCommerceNotConfigured, WooCommerceReadError, WooCommerceReadOnlyClient
from ai_os.woocommerce_actions import register_woocommerce_draft_adapter
from ai_os.agent_schemas import AgentOut, AgentProfileOut, PlanCreate, PlanOut
from ai_os.registry import get_agent, list_agents, load_agent_profile
from ai_os.departments import get_department, list_departments
from ai_os.department_management import get_company_overview, get_department_workload
from ai_os.department_coordination import (create_department_plan, get_department_plan, list_department_plans, review_department_plan)
from ai_os.ceo_delegation import delegate_ceo_selected_departments
from ai_os.orchestrator import build_plan
from ai_os.manual_schemas import WorkPacketCreate, WorkPacketOut, RuntimeStatus
from ai_os.work_packets import build_work_packet
from ai_os.queue_schemas import JobCreate, JobOut, WorkerRunOut
from ai_os.queue import enqueue_job, list_jobs
from ai_os.worker import run_once
from ai_os.worker_control import set_worker_desired_state, get_worker_status
from ai_os.agent_runtime import schedule_ready_steps
from ai_os.governance import evaluate_action
from ai_os.governance_schemas import GovernanceEvaluateIn, GovernanceEvaluateOut
from ai_os.runbooks import get_runbook, list_runbooks
from ai_os.execution_schemas import CompanyRunCreate, CompanyRunOut, StepReportCreate, StepOut
from ai_os.execution import create_company_run, list_company_runs, get_company_run, dispatch_ready_step, submit_step_report
from ai_os.ceo_schemas import CEOObjectiveCreate, CEOPlanOut
from ai_os.ceo_brain import create_ceo_plan, get_ceo_plan
from ai_os.model_adapter import get_model_status, ModelNotConfigured
from ai_os.ceo_review import review_company_run
from ai_os.identity import AgentIdentityError, consume_agent_token
from ai_os.knowledge_schemas import KnowledgeCreate, KnowledgeReview
from ai_os.research_schemas import ResearchSearchIn
from ai_os.research import (ResearchNotConfigured, ResearchProviderError, research_status, search_exa)
from ai_os.research_feed_schemas import FeedResearchIn
from ai_os.free_research import collect_release_feed_candidates
from ai_os.research_task_schemas import ResearchTaskProposalReview
from ai_os.research_planner import (draft_research_task_proposals, list_research_task_proposals, review_research_task_proposal)
from ai_os.evaluation import list_evaluations, evaluation_summary, evaluation_trends
from ai_os.knowledge import (create_knowledge_item, get_knowledge_item,
                            list_knowledge_items, review_knowledge_item)
from ai_os.improvement import (draft_improvement_proposals, list_improvement_proposals,
                               review_improvement_proposal)
from ai_os.improvement_testing import run_proposal_regression_tests, list_proposal_test_runs
from ai_os.instruction_versions import (
    activate_tested_proposal, get_active_instruction, get_instruction_history,
    rollback_instruction,
)
from ai_os.behavior_testing import (
    FIXTURES as BEHAVIOR_TEST_FIXTURES, get_behavior_test_status,
    list_behavior_test_runs, run_behavior_regression_test,
)
from ai_os.training_schemas import TrainingExampleCreate, TrainingExampleReview, TrainingDatasetExportRequest
from ai_os.training_data import (create_training_example, list_training_examples,
                                 review_training_example, export_training_dataset,
                                 list_training_dataset_exports)
from ai_os.action_gateway import get_action_gateway_status
from ai_os.control_plane import (initialize_control_plane, control_plane_overview,\n    list_control_plane_agents, get_control_plane_agent, set_agent_enabled,\n    list_control_plane_endpoints, create_control_plane_endpoint)\nfrom ai_os.control_plane_schemas import AgentEnableUpdate, EndpointCreate\n
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    initialize_control_plane()
    register_wordpress_draft_adapter()
    register_woocommerce_draft_adapter()
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

@app.get("/integrations/wordpress/status")
def get_wordpress_integration_status():
    """Owner-only configuration status; does not contact the WordPress site."""
    return WordPressReadOnlyClient.status()

@app.get("/integrations/wordpress/posts")
def get_wordpress_posts(page: int = Query(default=1, ge=1, le=1000),
                        per_page: int = Query(default=20, ge=1, le=50)):
    """Owner-only bounded WordPress post inventory; read-only."""
    try:
        return {"posts": WordPressReadOnlyClient.from_environment().list_posts(
            page=page, per_page=per_page
        )}
    except WordPressNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WordPressReadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/integrations/wordpress/pages")
def get_wordpress_pages(page: int = Query(default=1, ge=1, le=1000),
                        per_page: int = Query(default=20, ge=1, le=50)):
    """Owner-only bounded WordPress page inventory; read-only."""
    try:
        return {"pages": WordPressReadOnlyClient.from_environment().list_pages(
            page=page, per_page=per_page
        )}
    except WordPressNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WordPressReadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.get("/integrations/woocommerce/status")
def get_woocommerce_integration_status():
    """Owner-only configuration status; does not contact the store."""
    return WooCommerceReadOnlyClient.status()


@app.get("/integrations/woocommerce/products")
def get_woocommerce_products(page: int = Query(default=1, ge=1, le=1000),
                             per_page: int = Query(default=20, ge=1, le=50)):
    """Owner-only bounded WooCommerce product inventory; read-only."""
    try:
        return {"products": WooCommerceReadOnlyClient.from_environment().list_products(
            page=page, per_page=per_page
        )}
    except WooCommerceNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WooCommerceReadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/integrations/woocommerce/orders")
def get_woocommerce_order_statuses(
    page: int = Query(default=1, ge=1, le=1000),
    per_page: int = Query(default=20, ge=1, le=50),
    status: str | None = Query(default=None, max_length=20),
):
    """Owner-only minimized order status view; excludes customer/billing/shipping PII."""
    try:
        return {"orders": WooCommerceReadOnlyClient.from_environment().list_order_statuses(
            page=page, per_page=per_page, status=status
        )}
    except WooCommerceNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WooCommerceReadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/actions/gateway/status")
def get_action_gateway_readiness():
    return get_action_gateway_status()

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
        "external_actions_enabled": get_action_gateway_status()["enabled"],
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


@app.post("/improvement-proposals/{proposal_id}/activate", status_code=201)
def post_improvement_proposal_activate(proposal_id: str, request: Request):
    """Owner-authenticated activation of the exact proposal text after a passing static screen."""
    actor = getattr(request.state, "actor", "unknown")
    if actor != "owner":
        raise HTTPException(status_code=403, detail="A configured owner token is required to activate agent instructions.")
    try:
        version = activate_tested_proposal(proposal_id, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if version is None:
        raise HTTPException(status_code=404, detail="Improvement proposal not found")
    append_event(
        actor, "agent_instruction_activated", "agent_instruction_version", version["id"],
        {"agent_id": version["agent_id"], "version_number": version["version_number"],
         "proposal_id": proposal_id, "content_sha256": version["content_sha256"]},
    )
    return version


@app.get("/agents/{agent_id}/instructions")
def get_agent_active_instructions(agent_id: str):
    try:
        return get_active_instruction(agent_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/agents/{agent_id}/instructions/history")
def get_agent_instruction_history(agent_id: str, limit: int = Query(default=30, ge=1, le=100)):
    try:
        return get_instruction_history(agent_id, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/agents/{agent_id}/instructions/rollback")
def post_agent_instruction_rollback(agent_id: str, request: Request):
    actor = getattr(request.state, "actor", "unknown")
    if actor != "owner":
        raise HTTPException(status_code=403, detail="A configured owner token is required to roll back agent instructions.")
    try:
        version = rollback_instruction(agent_id, actor=actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    append_event(
        actor, "agent_instruction_rolled_back", "agent_instruction_version", version["id"],
        {"agent_id": agent_id, "version_number": version["version_number"]},
    )
    return version


@app.get("/behavior-tests/status")
def get_behavior_test_readiness():
    return {**get_behavior_test_status(), "fixtures": list(BEHAVIOR_TEST_FIXTURES)}


@app.post("/improvement-proposals/{proposal_id}/behavior-test", status_code=201)
def post_improvement_behavior_test(
    proposal_id: str, request: Request,
    fixture_id: str = Query(default="source-grounded-research", max_length=80),
):
    """Compare baseline and candidate prompts through the explicitly enabled local-only model."""
    actor = getattr(request.state, "actor", "unknown")
    if actor != "owner":
        raise HTTPException(status_code=403, detail="A configured owner token is required to run model behavior tests.")
    try:
        result = run_behavior_regression_test(proposal_id, fixture_id)
    except ModelNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Improvement proposal not found")
    append_event(
        actor, "instruction_behavior_tested", "improvement_proposal", proposal_id,
        {"test_run_id": result["id"], "fixture_id": fixture_id,
         "passed": result["passed"], "score_delta": result["score_delta"],
         "model": result["model"]},
    )
    return result


@app.get("/improvement-proposals/{proposal_id}/behavior-tests")
def get_improvement_behavior_tests(
    proposal_id: str, limit: int = Query(default=20, ge=1, le=100)
):
    return list_behavior_test_runs(proposal_id, limit=limit)


@app.post("/training-examples", status_code=201)
def post_training_example(payload: TrainingExampleCreate, request: Request):
    """Store an owner-attested candidate; accepted examples require a separate review."""
    actor = getattr(request.state, "actor", "unknown")
    try:
        item = create_training_example(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    append_event(
        actor, "model_training_example_created", "model_training_example", item["id"],
        {"task_family": item["task_family"], "status": item["status"],
         "source_count": len(item["source_refs"])},
    )
    return item


@app.get("/training-examples")
def get_training_examples(
    status: str | None = Query(default=None, pattern=r"^(candidate|accepted|rejected)$"),
    limit: int = Query(default=100, ge=1, le=500),
):
    return list_training_examples(status=status, limit=limit)


@app.post("/training-examples/{example_id}/review")
def post_training_example_review(
    example_id: str, payload: TrainingExampleReview, request: Request
):
    actor = getattr(request.state, "actor", "unknown")
    try:
        item = review_training_example(example_id, payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Training example not found")
    append_event(
        actor, "model_training_example_reviewed", "model_training_example", example_id,
        {"decision": payload.decision, "task_family": item["task_family"]},
    )
    return item


@app.post("/training-datasets/export", status_code=201)
def post_training_dataset_export(
    payload: TrainingDatasetExportRequest, request: Request
):
    """Export only owner-accepted examples; this endpoint does not train a model."""
    actor = getattr(request.state, "actor", "unknown")
    try:
        result = export_training_dataset(actor=actor, limit=payload.limit)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    append_event(
        actor, "model_training_dataset_exported", "training_dataset_export",
        result["export_id"],
        {"version_number": result["version_number"],
         "dataset_sha256": result["dataset_sha256"],
         "example_count": result["example_count"]},
    )
    return result


@app.get("/training-datasets/exports")
def get_training_dataset_exports(
    limit: int = Query(default=50, ge=1, le=200)
):
    return list_training_dataset_exports(limit=limit)


@app.get("/audit/verify")
def get_audit_verification():
    return verify_chain()




@app.get("/research/status")
def get_research_status():
    """Report configuration without exposing provider credentials."""
    return research_status()




@app.post("/research/task-proposals/draft")
def post_draft_research_task_proposals(limit: int = Query(default=20, ge=1, le=50)):
    """Ask the configured CEO model to turn accepted research into task proposals."""
    try:
        result = draft_research_task_proposals(limit=limit)
    except ModelNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="CEO returned an invalid task proposal response.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Configured CEO model request failed; no task proposal was created.") from exc
    append_event(
        "agent:company-orchestrator", "research_task_proposals_drafted",
        "research_task_proposal_batch", str(uuid4()),
        {"created": result.get("created", 0), "rejected": len(result.get("rejected", []))},
    )
    return result


@app.get("/research/task-proposals")
def get_research_task_proposals(
    status: str | None = Query(default=None, pattern=r"^(candidate|approved|rejected)$"),
    limit: int = Query(default=50, ge=1, le=200),
):
    return list_research_task_proposals(status=status, limit=limit)


@app.post("/research/task-proposals/{proposal_id}/review")
def post_review_research_task_proposal(
    proposal_id: str, payload: ResearchTaskProposalReview, request: Request
):
    actor = getattr(request.state, "actor", "unknown")
    if actor not in {"owner", "local-development"}:
        raise HTTPException(status_code=403, detail="Owner review is required.")
    try:
        proposal = review_research_task_proposal(
            proposal_id, decision=payload.decision, actor=actor, note=payload.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if proposal is None:
        raise HTTPException(status_code=404, detail="Research task proposal not found.")
    append_event(actor, "research_task_proposal_reviewed", "research_task_proposal",
                 proposal_id, {"decision": payload.decision, "task_id": proposal.get("task_id")})
    return proposal


@app.post("/research/feeds")
def post_research_feeds(payload: FeedResearchIn, request: Request):
    """Search only fixed public release feeds; save matches as untrusted candidates."""
    try:
        results = collect_release_feed_candidates(
            payload.query, max_per_feed=payload.max_per_feed
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    actor = getattr(request.state, "actor", "unknown")
    existing = {
        item["source_url"]
        for item in list_knowledge_items(limit=500)
        if item.get("source_url")
    }
    items = []
    duplicates = 0
    for result in results:
        if result["url"] in existing:
            duplicates += 1
            continue
        candidate = KnowledgeCreate(
            title=result["title"],
            content=result["excerpt"],
            category=payload.category,
            source_url=result["url"],
            source_title=result["source_title"],
            source_published_at=result.get("published_date"),
            confidence=0.5,
            tags=payload.tags,
        )
        item = create_knowledge_item(candidate, actor=actor)
        existing.add(result["url"])
        append_event(actor, "research_candidate_created", "knowledge_item", item["id"], {
            "source_url": item["source_url"], "query": payload.query[:200],
            "provider": "github_release_feeds",
        })
        items.append(item)
    append_event(actor, "research_feed_scan_completed", "research_query", str(uuid4()), {
        "provider": "github_release_feeds", "query": payload.query[:200],
        "results_received": len(results), "candidates_created": len(items),
        "duplicates_skipped": duplicates,
    })
    return {
        "provider": "github_release_feeds",
        "query": payload.query,
        "results_received": len(results),
        "candidates_created": len(items),
        "duplicates_skipped": duplicates,
        "items": items,
        "notice": "Free release-feed matches are unreviewed candidates, not verified facts.",
    }


@app.post("/research/search")
def post_research_search(payload: ResearchSearchIn, request: Request):
    """Run one explicitly requested, bounded, metered search and save candidates."""
    try:
        results = search_exa(payload.query, num_results=payload.num_results)
    except ResearchNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ResearchProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None

    actor = getattr(request.state, "actor", "unknown")
    items = []
    for result in results:
        try:
            candidate = KnowledgeCreate(
                title=result["title"],
                content=result["excerpt"],
                category=payload.category,
                source_url=result["url"],
                source_title=result["title"],
                source_published_at=result.get("published_date"),
                confidence=0.5,
                tags=payload.tags,
            )
        except Exception:
            continue
        item = create_knowledge_item(candidate, actor=actor)
        append_event(actor, "research_candidate_created", "knowledge_item", item["id"], {
            "source_url": item["source_url"], "query": payload.query[:200],
            "provider": "exa",
        })
        items.append(item)
    append_event(actor, "research_search_completed", "research_query", str(uuid4()), {
        "provider": "exa", "query": payload.query[:200],
        "results_received": len(results), "candidates_created": len(items),
    })
    return {
        "provider": "exa",
        "query": payload.query,
        "results_received": len(results),
        "candidates_created": len(items),
        "items": items,
        "notice": "All results are unreviewed candidates, not verified facts.",
    }


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

@app.post("/company-runs/{run_id}/departments/{department_id}/plan")
def post_department_manager_plan(run_id: str, department_id: str):
    """Ask the configured department manager to delegate bounded internal work."""
    try:
        return create_department_plan(run_id, department_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/company-runs/{run_id}/department-plans")
def get_department_manager_plans(run_id: str):
    if get_company_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Company run not found")
    return {"run_id": run_id, "plans": list_department_plans(run_id)}


@app.post("/company-runs/{run_id}/departments/{department_id}/review")
def post_department_manager_review(run_id: str, department_id: str):
    """Manager reviews completed delegated work and produces a CEO-facing report."""
    try:
        return review_department_plan(run_id, department_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/company/overview")
def get_company_coordination_overview():
    """CEO read-only overview of department workload, run status, and governance."""
    return get_company_overview()


@app.get("/company/departments/{department_id}/workload")
def get_company_department_workload(department_id: str):
    """Manager-facing read-only workload view for one department."""
    workload = get_department_workload(department_id)
    if workload is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return workload


@app.get("/company/departments")
def get_company_departments():
    """Read-only org chart; department managers are specialist assignments, not separate processes."""
    return {
        "accountable_agent_id": "company-orchestrator",
        "departments": list_departments(),
        "limitations": [
            "This directory defines department charters and resolves available specialist profiles.",
            "A manager assignment is not proof of an always-running manager process.",
            "Department-specific budgets, integrations, schedules, and independent autonomy are not enabled.",
            "All consequential external actions remain subject to CEO governance and owner approval.",
        ],
    }


@app.get("/company/departments/{department_id}")
def get_company_department(department_id: str):
    department = get_department(department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


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

@app.post("/ceo/plans/{run_id}/delegate")
def post_ceo_plan_department_delegation(run_id: str, request: Request):
    """CEO delegates only to department managers explicitly selected in its plan."""
    try:
        result = delegate_ceo_selected_departments(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    append_event(
        getattr(request.state, "actor", "unknown"),
        "ceo_department_delegation_completed", "company_run", run_id,
        {"selected_departments": result["selected_departments"],
         "delegation_count": len(result["delegations"])},
    )
    return result


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

@app.get("/worker/status")
def get_persistent_worker_status():
    return get_worker_status()


def _set_worker_state(state: str, request: Request):
    actor = getattr(request.state, "actor", "unknown")
    result = set_worker_desired_state(state, actor)
    append_event(actor, f"worker_{state}", "worker_control", "singleton",
                 {"desired_state": state})
    return {**get_worker_status(), "control": result}


@app.post("/worker/start")
def post_worker_start(request: Request):
    return _set_worker_state("running", request)


@app.post("/worker/pause")
def post_worker_pause(request: Request):
    return _set_worker_state("paused", request)


@app.post("/worker/resume")
def post_worker_resume(request: Request):
    return _set_worker_state("running", request)


@app.post("/worker/stop")
def post_worker_stop(request: Request):
    return _set_worker_state("stopped", request)


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

@app.post("/ceo/approval-requests", status_code=201)
def post_ceo_owner_approval_request(
    payload: CEOApprovalRequestCreate,
    agent_token: str | None = Header(default=None, alias="X-AI-Agent-Token"),
):
    """Accept an exact-scope approval request only from a signed CEO identity."""
    if not agent_token:
        raise HTTPException(status_code=401, detail="A signed CEO agent token is required.")
    try:
        approval = create_owner_approval_request(
            agent_token,
            action_type=payload.action_type,
            parameters=payload.parameters,
            ttl_seconds=payload.ttl_seconds,
        )
    except ApprovalSecurityError as exc:
        message = str(exc)
        status_code = 409 if "existing company run" in message else 403
        raise HTTPException(status_code=status_code, detail=message) from exc
    append_event(
        "agent:company-orchestrator", "owner_approval_requested",
        "owner_approval_request", approval["id"],
        {"run_id": approval["run_id"], "action_type": approval["action_type"],
         "action_hash": approval["action_hash"], "expires_at": approval["expires_at"]},
    )
    return approval


@app.get("/owner/approval-requests")
def get_owner_approval_requests(
    status: str | None = Query(
        default=None,
        pattern=r"^(pending|approved|rejected|consumed|expired)$",
    ),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Owner-only inbox for exact-scope CEO requests."""
    return list_owner_approval_requests(status=status, limit=limit)


@app.post("/owner/approval-requests/{approval_id}/decision")
def post_owner_approval_decision(
    approval_id: str, payload: OwnerApprovalDecision, request: Request
):
    """Record an explicit owner decision against the exact displayed action hash."""
    actor = getattr(request.state, "actor", "unknown")
    if actor != "owner":
        raise HTTPException(status_code=403, detail="A configured owner token is required.")
    try:
        approval = decide_owner_approval(
            approval_id,
            action_hash=payload.action_hash,
            decision=payload.decision,
        )
    except ApprovalSecurityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Owner approval request not found.")
    append_event(
        actor, "owner_approval_decided", "owner_approval_request", approval_id,
        {"decision": payload.decision, "action_hash": approval["action_hash"]},
    )
    return approval


@app.post("/owner/approval-requests/{approval_id}/execute")
def post_execute_owner_approved_action(approval_id: str, request: Request):
    """Execute an already-approved exact-scope action through a trusted adapter."""
    if getattr(request.state, "actor", "unknown") != "owner":
        raise HTTPException(status_code=403, detail="A configured owner token is required.")
    approvals = list_owner_approval_requests(status="approved", limit=500)
    approval = next((item for item in approvals if item["id"] == approval_id), None)
    if approval is None:
        raise HTTPException(status_code=409, detail="No unexpired approved action was found.")
    try:
        result = execute_approved_action(
            approval_id,
            action_type=approval["action_type"],
            parameters=approval["parameters"],
            execution_id=str(uuid4()),
        )
    except ActionGatewayError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    append_event(
        "owner", "owner_approved_action_executed", "owner_approval_request",
        approval_id, {"action_type": approval["action_type"], "execution_id": result["execution_id"]},
    )
    return result


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


# Agent Control Plane — CP-1 registry APIs. All routes inherit owner-token auth.
@app.get("/control-plane")
def get_control_plane_status():
    return control_plane_overview()


@app.get("/control-plane/agents")
def get_control_plane_agents(
    department: str | None = Query(default=None, max_length=100),
    enabled: bool | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
):
    return {"agents": list_control_plane_agents(
        department=department, enabled=enabled, limit=limit
    )}


@app.get("/control-plane/agents/{agent_id}")
def get_control_plane_agent_detail(agent_id: str):
    agent = get_control_plane_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Registered agent not found")
    return agent


@app.patch("/control-plane/agents/{agent_id}")
def patch_control_plane_agent(agent_id: str, payload: AgentEnableUpdate, request: Request):
    actor = getattr(request.state, "actor", "unknown")
    try:
        agent = set_agent_enabled(agent_id, payload.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if agent is None:
        raise HTTPException(status_code=404, detail="Registered agent not found")
    append_event(
        actor, "control_plane_agent_enabled" if payload.enabled else "control_plane_agent_disabled",
        "control_plane_agent", agent_id, {"enabled": payload.enabled},
    )
    return agent


@app.get("/control-plane/endpoints")
def get_control_plane_endpoints():
    return {"endpoints": list_control_plane_endpoints(),
            "notice": "New network endpoints are registered disabled; CP-1 does not connect to them."}


@app.post("/control-plane/endpoints", status_code=201)
def post_control_plane_endpoint(payload: EndpointCreate, request: Request):
    try:
        endpoint = create_control_plane_endpoint(
            name=payload.name, protocol=payload.protocol, base_url=payload.base_url,
            credential_ref=payload.credential_ref, metadata=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    append_event(
        getattr(request.state, "actor", "unknown"), "control_plane_endpoint_registered",
        "control_plane_endpoint", endpoint["endpoint_id"],
        {"protocol": endpoint["protocol"], "enabled": endpoint["enabled"],
         "has_credential_reference": bool(endpoint["credential_ref"])},
    )
    return endpoint
