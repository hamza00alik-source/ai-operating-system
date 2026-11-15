"""Owner-authenticated API for OpenCompany AI Brain planning and status.

Planning is a preview only. It does not enqueue work, call models, or bypass
existing owner-approved delegation and worker execution controls.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from opencompany_core.domain import BUSINESS_UNIT_IDS
from opencompany_core.model_gateway import NoEligibleProvider
from opencompany_core.orchestration import (
    AgentTaskSpec,
    OpenCompanyOrchestrator,
    ReasoningEffort,
    RoutingRequest,
    TaskComplexity,
    TaskKind,
)
from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime

router = APIRouter()


class BrainTaskInput(BaseModel):
    task_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    role_key: str = Field(min_length=1, max_length=160)
    department: str = Field(min_length=1, max_length=80)
    objective: str = Field(min_length=1, max_length=4000)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    required_capabilities: list[str] = Field(default_factory=list, max_length=30)


class BrainPlanPreviewInput(BaseModel):
    business_id: str = "core"
    tasks: list[BrainTaskInput] = Field(min_length=1, max_length=50)
    max_parallel_agents: int = Field(default=3, ge=1, le=10)
    max_attempts_per_task: int = Field(default=2, ge=1, le=3)


class BrainRoutePreviewInput(BaseModel):
    task_kind: TaskKind
    complexity: TaskComplexity
    estimated_context_tokens: int = Field(ge=1, le=1_000_000)
    required_capabilities: list[str] = Field(default_factory=list, max_length=30)
    business_id: str = "core"


@router.get("/orchestration/brain/status", dependencies=[Depends(require_owner_key)])
def brain_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Expose safe orchestration readiness without revealing provider credentials."""
    try:
        eligible = list(runtime.gateway.eligible_providers(request_budget_usd=0.0))
    except Exception:
        eligible = []
    return {
        "brain": "opencompany",
        "planning_available": True,
        "eligible_zero_cost_providers": eligible,
        "gateway_enabled": bool(eligible),
        "request_budget_usd": 0.0,
        "paid_fallback": False,
        "model_calls_performed": False,
        "external_actions_performed": False,
        "owner_approval_required_for_execution": True,
        "note": (
            "Provider eligibility is not proof of live model availability. "
            "Run the existing owner-controlled provider test before starting workers."
        ),
    }


@router.post("/orchestration/brain/plan-preview", dependencies=[Depends(require_owner_key)])
def brain_plan_preview(payload: BrainPlanPreviewInput) -> dict:
    """Validate a bounded multi-agent dependency graph and return execution batches."""
    if payload.business_id not in BUSINESS_UNIT_IDS:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    try:
        tasks = tuple(
            AgentTaskSpec(
                task_id=item.task_id,
                role_key=item.role_key,
                department=item.department,
                objective=item.objective,
                depends_on=tuple(item.depends_on),
                required_capabilities=frozenset(item.required_capabilities),
            )
            for item in payload.tasks
        )
        plan = OpenCompanyOrchestrator.create_plan(
            payload.business_id, tasks,
            max_parallel_agents=payload.max_parallel_agents,
            max_attempts_per_task=payload.max_attempts_per_task,
        )
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "business_id": plan.business_id,
        "task_count": len(plan.tasks),
        "max_parallel_agents": plan.max_parallel_agents,
        "max_attempts_per_task": plan.max_attempts_per_task,
        "batches": [list(batch) for batch in plan.topological_batches()],
        "tasks": [
            {
                "task_id": task.task_id,
                "role_key": task.role_key,
                "department": task.department,
                "depends_on": list(task.depends_on),
                "required_capabilities": sorted(task.required_capabilities),
                "review_required": task.review_required,
            }
            for task in plan.tasks
        ],
        "execution_started": False,
        "queue_entries_created": False,
        "owner_approval_required": True,
    }
