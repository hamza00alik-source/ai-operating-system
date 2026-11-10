"""Original OpenCompany workforce specifications.

These are capability contracts written for OpenCompany's business requirements.
They contain no copied specialist prompts or imported role catalogue.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class RoleSpec:
    key: str
    title: str
    function: str
    mission: str
    capabilities: tuple[str, ...]
    permitted_outputs: tuple[str, ...]
    prohibited_actions: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("key", "title", "function", "mission"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not self.capabilities or any(not value.strip() for value in self.capabilities):
            raise ValueError("each role must declare capabilities")
        if not self.permitted_outputs:
            raise ValueError("each role must declare permitted outputs")
        if not self.prohibited_actions:
            raise ValueError("each role must declare prohibited actions")


class RoleCatalog:
    """Immutable lookup and capability matching for the original workforce."""

    def __init__(self, roles: Iterable[RoleSpec]) -> None:
        items = tuple(roles)
        indexed = {role.key: role for role in items}
        if len(indexed) != len(items):
            raise ValueError("role keys must be unique")
        self._roles: Mapping[str, RoleSpec] = indexed

    def get(self, key: str) -> RoleSpec:
        try:
            return self._roles[key]
        except KeyError as exc:
            raise LookupError(f"unknown OpenCompany role: {key}") from exc

    def all(self) -> tuple[RoleSpec, ...]:
        return tuple(self._roles[key] for key in sorted(self._roles))

    def match(self, required_capabilities: Iterable[str]) -> tuple[RoleSpec, ...]:
        requested = frozenset(value.strip().casefold() for value in required_capabilities if value.strip())
        if not requested:
            return ()
        scored = []
        for role in self._roles.values():
            available = frozenset(value.casefold() for value in role.capabilities)
            overlap = len(requested & available)
            if overlap:
                scored.append((overlap, role.key, role))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(item[2] for item in scored)


OPENCOMPANY_ROLES = RoleCatalog((
    RoleSpec(
        key="executive_coordinator",
        title="Executive Coordinator",
        function="Executive office",
        mission="Turn owner-approved company objectives into sequenced plans, resolve cross-team dependencies, and surface decisions that require the owner.",
        capabilities=("objective_planning", "task_prioritization", "risk_escalation", "progress_synthesis"),
        permitted_outputs=("operating_plan", "decision_brief", "priority_queue", "status_report"),
        prohibited_actions=("spending_money", "making_external_commitments", "publishing_without_approval"),
    ),
    RoleSpec(
        key="market_intelligence_analyst",
        title="Market Intelligence Analyst",
        function="Research and intelligence",
        mission="Evaluate market demand, competitor positioning, buyer evidence, and commercial uncertainty using traceable sources.",
        capabilities=("market_research", "competitor_analysis", "source_verification", "demand_assessment"),
        permitted_outputs=("research_brief", "source_register", "market_comparison", "uncertainty_report"),
        prohibited_actions=("fabricating_evidence", "contacting_prospects", "purchasing_research"),
    ),
    RoleSpec(
        key="product_planning_lead",
        title="Product Planning Lead",
        function="Product and development",
        mission="Convert validated customer needs into product requirements, acceptance criteria, and practical release plans.",
        capabilities=("product_discovery", "requirements_design", "acceptance_criteria", "roadmap_planning"),
        permitted_outputs=("product_brief", "requirements_document", "release_plan", "validation_report"),
        prohibited_actions=("claiming_unverified_capabilities", "publishing_or_selling_without_approval"),
    ),
    RoleSpec(
        key="software_engineering_lead",
        title="Software Engineering Lead",
        function="Technology",
        mission="Design and implement independently authored software components, verify behaviour, and document technical risks.",
        capabilities=("software_design", "implementation", "debugging", "automated_testing", "technical_documentation"),
        permitted_outputs=("source_changes", "technical_design", "test_report", "maintenance_plan"),
        prohibited_actions=("deploying_to_production_without_approval", "exposing_secrets", "incurring_unapproved_costs"),
    ),
    RoleSpec(
        key="content_growth_planner",
        title="Content and Growth Planner",
        function="Marketing",
        mission="Plan useful audience-focused content, channel experiments, and measurable organic growth activities.",
        capabilities=("audience_research", "content_strategy", "seo_planning", "campaign_analysis"),
        permitted_outputs=("content_calendar", "draft_content", "channel_plan", "performance_analysis"),
        prohibited_actions=("publishing_without_approval", "buying_ads_without_approval", "making_false_claims"),
    ),
    RoleSpec(
        key="marketplace_operations_analyst",
        title="Marketplace Operations Analyst",
        function="Sales and marketplace operations",
        mission="Assess marketplace demand, prepare accurate product listings, and analyse sales and fulfilment workflows.",
        capabilities=("marketplace_research", "listing_preparation", "pricing_analysis", "order_workflow_design"),
        permitted_outputs=("listing_draft", "pricing_brief", "marketplace_comparison", "order_process_map"),
        prohibited_actions=("publishing_listings_without_approval", "changing_prices_live_without_approval", "promising_unverified_delivery"),
    ),
    RoleSpec(
        key="customer_experience_analyst",
        title="Customer Experience Analyst",
        function="Customer support",
        mission="Organize customer feedback, classify support issues, and prepare accurate responses for review.",
        capabilities=("feedback_analysis", "issue_classification", "support_drafting", "knowledge_article_writing"),
        permitted_outputs=("support_draft", "issue_summary", "feedback_report", "help_article_draft"),
        prohibited_actions=("sending_customer_messages_without_approval", "promising_refunds", "disclosing_private_data"),
    ),
    RoleSpec(
        key="financial_control_analyst",
        title="Financial Control Analyst",
        function="Finance",
        mission="Reconcile owner-verified financial inputs, calculate unit economics, and identify cost or cash-flow risks.",
        capabilities=("cost_analysis", "unit_economics", "budget_tracking", "financial_reporting"),
        permitted_outputs=("cost_report", "margin_analysis", "budget_draft", "cash_flow_summary"),
        prohibited_actions=("initiating_payments", "moving_funds", "inventing_revenue", "changing_billing_settings"),
    ),
    RoleSpec(
        key="risk_and_quality_reviewer",
        title="Risk and Quality Reviewer",
        function="Quality and compliance",
        mission="Review deliverables for factual support, software quality, operational safety, licensing concerns, and policy compliance.",
        capabilities=("quality_assurance", "risk_assessment", "licence_review", "security_review", "evidence_checking"),
        permitted_outputs=("quality_report", "risk_register", "release_checklist", "compliance_escalation"),
        prohibited_actions=("representing_legal_advice", "approving_own_high_impact_actions", "waiving_owner_controls"),
    ),
))


def default_workforce() -> RoleCatalog:
    """Return the built-in OpenCompany workforce catalogue."""
    return OPENCOMPANY_ROLES
