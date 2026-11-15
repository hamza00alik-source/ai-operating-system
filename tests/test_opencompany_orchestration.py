import pytest

from opencompany_core.model_gateway import BillingMode
from opencompany_core.orchestration import (
    AgentTaskSpec,
    ModelCandidate,
    NoEligibleRoute,
    OpenCompanyOrchestrator,
    ReasoningEffort,
    RoutingRequest,
    TaskComplexity,
    TaskKind,
)


def candidate(provider, model, **kwargs):
    kwargs.setdefault("max_context_tokens", 32768)
    kwargs.setdefault("reasoning_effort", ReasoningEffort.STANDARD)
    return ModelCandidate(provider=provider, model=model, billing_mode=BillingMode.FREE_CONFIRMED, **kwargs)


def test_routine_routing_prefers_fastest_eligible_free_model():
    fast = candidate("free-a", "fast", latency_tier=1, quality_tier=2)
    strong = candidate("free-b", "strong", latency_tier=3, quality_tier=5)
    request = RoutingRequest(TaskKind.RESEARCH, TaskComplexity.ROUTINE, 1000)
    decision = OpenCompanyOrchestrator.route(request, [strong, fast])
    assert (decision.provider, decision.model) == ("free-a", "fast")
    assert decision.cost_ceiling_usd == 0


def test_complex_routing_prefers_quality_and_high_reasoning():
    balanced = candidate(
        "free-a", "balanced", quality_tier=3, reasoning_effort=ReasoningEffort.HIGH
    )
    strongest = candidate(
        "free-b", "strongest", quality_tier=5, reasoning_effort=ReasoningEffort.MAXIMUM
    )
    request = RoutingRequest(TaskKind.ENGINEERING, TaskComplexity.CRITICAL, 12000)
    decision = OpenCompanyOrchestrator.route(request, [balanced, strongest])
    assert (decision.provider, decision.model) == ("free-b", "strongest")


def test_paid_and_unknown_billing_are_never_used_even_if_they_are_best():
    paid = ModelCandidate(
        "paid", "best", BillingMode.PAID_OWNER_APPROVED,
        max_cost_per_request_usd=1.0, quality_tier=5,
        reasoning_effort=ReasoningEffort.MAXIMUM,
    )
    unknown = ModelCandidate("unknown", "maybe-free", BillingMode.DISABLED)
    request = RoutingRequest(TaskKind.ANALYSIS, TaskComplexity.ROUTINE, 100)
    with pytest.raises(NoEligibleRoute, match="No paid fallback was attempted"):
        OpenCompanyOrchestrator.route(request, [paid, unknown])


def test_routing_requires_capabilities_task_fit_and_sufficient_context():
    unsuitable = candidate(
        "free", "small", supported_tasks=frozenset({TaskKind.CREATIVE}),
        capabilities=frozenset({"image"}), max_context_tokens=500,
    )
    request = RoutingRequest(
        TaskKind.RESEARCH, TaskComplexity.STANDARD, 1000,
        required_capabilities=frozenset({"web-research"}),
    )
    with pytest.raises(NoEligibleRoute):
        OpenCompanyOrchestrator.route(request, [unsuitable])


def test_zero_cost_request_budget_is_enforced():
    with pytest.raises(ValueError, match="zero-cost"):
        RoutingRequest(TaskKind.REVIEW, TaskComplexity.STANDARD, 100, request_budget_usd=0.01)


def test_team_plan_builds_dependency_batches_with_parallel_limit():
    tasks = (
        AgentTaskSpec("research-a", "researcher_a", "research", "Collect market evidence"),
        AgentTaskSpec("research-b", "researcher_b", "research", "Collect competitor evidence"),
        AgentTaskSpec("synthesis", "analyst", "research", "Synthesize findings",
                      depends_on=("research-a", "research-b")),
        AgentTaskSpec("review", "reviewer", "quality", "Review evidence",
                      depends_on=("synthesis",)),
    )
    plan = OpenCompanyOrchestrator.create_plan(
        "digital-products", tasks, max_parallel_agents=1
    )
    assert plan.topological_batches() == (
        ("research-a",), ("research-b",), ("synthesis",), ("review",)
    )


def test_team_plan_rejects_cycles_and_unknown_dependencies():
    with pytest.raises(ValueError, match="cycle"):
        OpenCompanyOrchestrator.create_plan("digital-products", (
            AgentTaskSpec("a", "role_a", "engineering", "A", depends_on=("b",)),
            AgentTaskSpec("b", "role_b", "engineering", "B", depends_on=("a",)),
        ))
    with pytest.raises(ValueError, match="unknown dependencies"):
        OpenCompanyOrchestrator.create_plan("digital-products", (
            AgentTaskSpec("a", "role_a", "engineering", "A", depends_on=("missing",)),
        ))


def test_team_plan_keeps_owner_review_mandatory():
    with pytest.raises(ValueError, match="review-required"):
        AgentTaskSpec("task", "role", "department", "Objective", review_required=False)


def test_team_plan_rejects_invalid_business_scope_and_parallelism():
    task = AgentTaskSpec("task", "role", "department", "Objective")
    with pytest.raises(ValueError, match="business unit"):
        OpenCompanyOrchestrator.create_plan("other-company", (task,))
    with pytest.raises(ValueError, match="max_parallel_agents"):
        OpenCompanyOrchestrator.create_plan("digital-products", (task,), max_parallel_agents=0)



def test_unknown_context_and_reasoning_metadata_are_not_assumed():
    unknown_context = candidate("free", "unknown-context", max_context_tokens=None)
    unknown_reasoning = candidate("free", "unknown-reasoning", reasoning_effort=None)
    request = RoutingRequest(TaskKind.RESEARCH, TaskComplexity.ROUTINE, 100)
    with pytest.raises(NoEligibleRoute, match="No paid fallback was attempted"):
        OpenCompanyOrchestrator.route(request, [unknown_context, unknown_reasoning])


def test_unknown_quality_and_latency_are_ranked_below_measured_values():
    unknown = candidate("free-a", "unknown-performance", quality_tier=None, latency_tier=None)
    measured = candidate("free-b", "measured", quality_tier=1, latency_tier=1)
    request = RoutingRequest(TaskKind.RESEARCH, TaskComplexity.ROUTINE, 100)
    decision = OpenCompanyOrchestrator.route(request, [unknown, measured])
    assert decision.model == "measured"
