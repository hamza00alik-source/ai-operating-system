"""Policy-first AI routing and bounded multi-agent planning for OpenCompany.

This module is deliberately deterministic and side-effect free. It does not call
providers, create queue entries, approve work, or perform external actions.
Execution remains with the existing supervised worker and owner-approval paths.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Iterable

from .domain import BUSINESS_UNIT_IDS
from .model_gateway import BillingMode


class TaskKind(StrEnum):
    RESEARCH = "research"
    ANALYSIS = "analysis"
    ENGINEERING = "engineering"
    CREATIVE = "creative"
    OPERATIONS = "operations"
    REVIEW = "review"


class TaskComplexity(IntEnum):
    ROUTINE = 1
    STANDARD = 2
    COMPLEX = 3
    CRITICAL = 4


class ReasoningEffort(IntEnum):
    LOW = 1
    STANDARD = 2
    HIGH = 3
    MAXIMUM = 4


_MIN_EFFORT = {
    TaskComplexity.ROUTINE: ReasoningEffort.LOW,
    TaskComplexity.STANDARD: ReasoningEffort.STANDARD,
    TaskComplexity.COMPLEX: ReasoningEffort.HIGH,
    TaskComplexity.CRITICAL: ReasoningEffort.MAXIMUM,
}


class NoEligibleRoute(RuntimeError):
    """No configured, confirmed-free model satisfies a task's routing policy."""


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    provider: str
    model: str
    billing_mode: BillingMode
    max_cost_per_request_usd: float = 0.0
    supported_tasks: frozenset[TaskKind] = frozenset()
    capabilities: frozenset[str] = frozenset()
    max_context_tokens: int | None = None
    reasoning_effort: ReasoningEffort | None = None
    quality_tier: int | None = None
    latency_tier: int | None = None
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("provider and model are required")
        if not math.isfinite(self.max_cost_per_request_usd) or self.max_cost_per_request_usd < 0:
            raise ValueError("model cost ceiling must be finite and non-negative")
        if self.max_context_tokens is not None and self.max_context_tokens < 1:
            raise ValueError("model context capacity must be positive when known")
        if self.quality_tier is not None and not 1 <= self.quality_tier <= 5:
            raise ValueError("quality tier must be between 1 and 5 when known")
        if self.latency_tier is not None and not 1 <= self.latency_tier <= 5:
            raise ValueError("latency tier must be between 1 and 5 when known")
        if self.billing_mode == BillingMode.FREE_CONFIRMED and self.max_cost_per_request_usd != 0:
            raise ValueError("confirmed-free models must have a zero cost ceiling")


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    task_kind: TaskKind
    complexity: TaskComplexity
    estimated_context_tokens: int
    required_capabilities: frozenset[str] = frozenset()
    business_id: str = "physical-agency"
    request_budget_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.business_id not in BUSINESS_UNIT_IDS:
            raise ValueError("unknown business unit")
        if self.estimated_context_tokens < 1:
            raise ValueError("estimated context tokens must be positive")
        if not math.isfinite(self.request_budget_usd) or self.request_budget_usd < 0:
            raise ValueError("request budget must be finite and non-negative")
        if self.request_budget_usd != 0:
            raise ValueError("OpenCompany zero-cost mode does not permit a non-zero request budget")
        if any(not value.strip() for value in self.required_capabilities):
            raise ValueError("required capabilities cannot contain empty values")


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    provider: str
    model: str
    reason: str
    candidates_considered: int
    business_id: str
    cost_ceiling_usd: float = 0.0


def route_model(
    request: RoutingRequest, candidates: Iterable[ModelCandidate]
) -> RoutingDecision:
    """Choose a suitable free model; paid/unknown billing is never a fallback.

    Routine tasks prioritize latency. Complex tasks prioritize quality and
    reasoning depth. All choices are stable and reproducible for equal inputs.
    """
    all_candidates = tuple(candidates)
    eligible = []
    minimum_effort = _MIN_EFFORT[request.complexity]
    for candidate in all_candidates:
        if candidate.billing_mode != BillingMode.FREE_CONFIRMED:
            continue
        if candidate.max_cost_per_request_usd != 0:
            continue
        # Unknown provider metadata is not evidence of sufficient capacity or
        # reasoning. Keep such candidates out rather than inheriting optimistic defaults.
        if candidate.max_context_tokens is None or candidate.max_context_tokens < request.estimated_context_tokens:
            continue
        if candidate.reasoning_effort is None or candidate.reasoning_effort < minimum_effort:
            continue
        if candidate.supported_tasks and request.task_kind not in candidate.supported_tasks:
            continue
        if not request.required_capabilities.issubset(candidate.capabilities):
            continue
        eligible.append(candidate)
    if not eligible:
        raise NoEligibleRoute(
            "No confirmed-free model satisfies task type, capabilities, context, "
            "reasoning effort and the USD 0 budget. No paid fallback was attempted."
        )
    if request.complexity <= TaskComplexity.STANDARD:
        eligible.sort(key=lambda item: (
            item.latency_tier if item.latency_tier is not None else 6,
            -(item.quality_tier if item.quality_tier is not None else 0),
            item.priority, item.provider, item.model
        ))
        reason = "routine-task route: latency first, then quality and configured priority"
    else:
        eligible.sort(key=lambda item: (
            -(item.quality_tier if item.quality_tier is not None else 0),
            -int(item.reasoning_effort), item.priority,
            item.latency_tier if item.latency_tier is not None else 6,
            item.provider, item.model
        ))
        reason = "complex-task route: quality and reasoning first, then configured priority"
    selected = eligible[0]
    return RoutingDecision(
        provider=selected.provider,
        model=selected.model,
        reason=reason,
        candidates_considered=len(all_candidates),
        business_id=request.business_id,
    )


@dataclass(frozen=True, slots=True)
class AgentTaskSpec:
    task_id: str
    role_key: str
    department: str
    objective: str
    depends_on: tuple[str, ...] = ()
    required_capabilities: frozenset[str] = frozenset()
    review_required: bool = True

    def __post_init__(self) -> None:
        for field_name in ("task_id", "role_key", "department", "objective"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} is required")
        if not self.review_required:
            raise ValueError("all agent deliverables must remain review-required")
        if self.task_id in self.depends_on:
            raise ValueError("a task cannot depend on itself")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("task dependencies must be unique")


@dataclass(frozen=True, slots=True)
class AgentTeamPlan:
    business_id: str
    tasks: tuple[AgentTaskSpec, ...]
    max_parallel_agents: int = 3
    max_attempts_per_task: int = 2

    def __post_init__(self) -> None:
        if self.business_id not in BUSINESS_UNIT_IDS:
            raise ValueError("unknown business unit")
        if not self.tasks:
            raise ValueError("a team plan must contain at least one task")
        if not 1 <= self.max_parallel_agents <= 20:
            raise ValueError("max_parallel_agents must be between 1 and 20")
        if not 1 <= self.max_attempts_per_task <= 3:
            raise ValueError("max_attempts_per_task must be between 1 and 3")
        ids = [task.task_id for task in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("task identifiers must be unique")
        known = set(ids)
        for task in self.tasks:
            missing = set(task.depends_on) - known
            if missing:
                raise ValueError(f"task {task.task_id} has unknown dependencies: {sorted(missing)}")
        # A cycle check also guarantees topological_batches always makes progress.
        self.topological_batches()

    def topological_batches(self) -> tuple[tuple[str, ...], ...]:
        pending = {task.task_id: set(task.depends_on) for task in self.tasks}
        batches: list[tuple[str, ...]] = []
        completed: set[str] = set()
        while pending:
            ready = tuple(sorted(
                task_id for task_id, dependencies in pending.items()
                if dependencies.issubset(completed)
            ))
            if not ready:
                raise ValueError("team plan contains a dependency cycle")
            for offset in range(0, len(ready), self.max_parallel_agents):
                batches.append(ready[offset:offset + self.max_parallel_agents])
            completed.update(ready)
            for task_id in ready:
                pending.pop(task_id)
        return tuple(batches)


class OpenCompanyOrchestrator:
    """Builds bounded plans and routes models without executing side effects."""

    @staticmethod
    def create_plan(
        business_id: str,
        tasks: Iterable[AgentTaskSpec],
        *,
        max_parallel_agents: int = 3,
        max_attempts_per_task: int = 2,
    ) -> AgentTeamPlan:
        return AgentTeamPlan(
            business_id=business_id,
            tasks=tuple(tasks),
            max_parallel_agents=max_parallel_agents,
            max_attempts_per_task=max_attempts_per_task,
        )

    @staticmethod
    def route(request: RoutingRequest, candidates: Iterable[ModelCandidate]) -> RoutingDecision:
        return route_model(request, candidates)
