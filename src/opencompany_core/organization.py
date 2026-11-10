"""Independent organizational design for OpenCompany.

This catalogue is authored from OpenCompany's own operating requirements. It
contains no imported department taxonomy or third-party agent instructions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .workforce import RoleCatalog, default_workforce, specialist_role_keys


@dataclass(frozen=True, slots=True)
class DepartmentSpec:
    key: str
    name: str
    mission: str
    accountabilities: tuple[str, ...]
    manager_role_key: str
    role_keys: tuple[str, ...]
    decision_scope: tuple[str, ...]
    success_measures: tuple[str, ...]
    approval_boundaries: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("key", "name", "mission", "manager_role_key"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        for field_name in ("accountabilities", "role_keys", "decision_scope",
                           "success_measures", "approval_boundaries"):
            values = getattr(self, field_name)
            if not values or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty entries")
        if self.manager_role_key not in self.role_keys:
            raise ValueError("department manager role must be included in role_keys")


class OrganizationCatalog:
    """Validated department registry with deterministic lookup."""

    def __init__(
        self,
        departments: Iterable[DepartmentSpec],
        workforce: RoleCatalog | None = None,
    ) -> None:
        entries = tuple(departments)
        indexed = {entry.key: entry for entry in entries}
        if len(indexed) != len(entries):
            raise ValueError("department keys must be unique")
        roles = workforce or default_workforce()
        for department in entries:
            for role_key in department.role_keys:
                roles.get(role_key)
        self._departments: Mapping[str, DepartmentSpec] = indexed

    def get(self, key: str) -> DepartmentSpec:
        try:
            return self._departments[key]
        except KeyError as exc:
            raise LookupError(f"unknown OpenCompany department: {key}") from exc

    def all(self) -> tuple[DepartmentSpec, ...]:
        return tuple(self._departments[key] for key in sorted(self._departments))

    def by_role(self, role_key: str) -> tuple[DepartmentSpec, ...]:
        return tuple(item for item in self.all() if role_key in item.role_keys)


OPENCOMPANY_DEPARTMENTS = OrganizationCatalog((
    DepartmentSpec(
        key="executive-office", name="Executive Office",
        mission="Translate the owner's goals into a coherent company agenda and coordinate decisions across departments.",
        accountabilities=("company priorities", "cross-department planning", "decision briefs", "owner escalation"),
        manager_role_key="executive_coordinator",
        role_keys=("executive_coordinator", *specialist_role_keys("executive-office")),
        decision_scope=("sequence internal work", "resolve routine priority conflicts", "request owner decisions"),
        success_measures=("priority completion rate", "decision turnaround", "cross-team dependency age"),
        approval_boundaries=("No agent may replace the owner's approval for protected actions.",),
    ),
    DepartmentSpec(
        key="intelligence-research", name="Intelligence & Research",
        mission="Reduce commercial uncertainty through traceable research and evidence-led opportunity assessment.",
        accountabilities=("market demand", "competitor monitoring", "source verification", "customer problem evidence"),
        manager_role_key="market_intelligence_analyst",
        role_keys=("market_intelligence_analyst", *specialist_role_keys("intelligence-research")),
        decision_scope=("research methods", "source quality ratings", "research priorities"),
        success_measures=("source coverage", "evidence freshness", "validated opportunity rate"),
        approval_boundaries=("Research does not authorize prospect contact, purchases, or paid data access.",),
    ),
    DepartmentSpec(
        key="product-innovation", name="Product & Innovation",
        mission="Turn validated opportunities into useful products, experiments, and measurable release plans.",
        accountabilities=("product discovery", "requirements", "prototypes", "acceptance criteria"),
        manager_role_key="product_planning_lead",
        role_keys=("product_planning_lead", *specialist_role_keys("product-innovation")),
        decision_scope=("draft requirements", "recommend product priorities", "design non-production experiments"),
        success_measures=("validated problem rate", "prototype cycle time", "acceptance-test coverage"),
        approval_boundaries=("Commercial release, listing, and customer promises require owner approval.",),
    ),
    DepartmentSpec(
        key="engineering-ai-systems", name="Engineering & AI Systems",
        mission="Build, operate, secure, and improve OpenCompany's independently authored software and AI infrastructure.",
        accountabilities=("AI runtime", "software delivery", "model and tool adapters", "reliability and security"),
        manager_role_key="software_engineering_lead",
        role_keys=("software_engineering_lead", *specialist_role_keys("engineering-ai-systems")),
        decision_scope=("isolated development changes", "automated tests", "non-production technical experiments"),
        success_measures=("test pass rate", "service reliability", "change failure rate", "security findings"),
        approval_boundaries=("Production deployment, credential changes, and paid infrastructure require separate owner approval.",),
    ),
    DepartmentSpec(
        key="media-creative-production", name="Media & Creative Production",
        mission="Produce original multimedia assets and content drafts for approved company initiatives.",
        accountabilities=("video concepts and scripts", "video and image production", "editing and packaging", "asset provenance"),
        manager_role_key="media_production_lead",
        role_keys=("media_production_lead", "content_growth_planner", *specialist_role_keys("media-creative-production")),
        decision_scope=("draft scripts", "prepare storyboards", "generate non-published draft assets when a zero-cost route is configured"),
        success_measures=("draft asset completion", "review acceptance rate", "production time", "asset rights coverage"),
        approval_boundaries=("Paid generation, licensing commitments, and publishing require owner approval.",),
    ),
    DepartmentSpec(
        key="marketing-audience-growth", name="Marketing & Audience Growth",
        mission="Earn relevant attention through useful content, search visibility, channel strategy, and measured experiments.",
        accountabilities=("audience research", "content strategy", "SEO", "campaign measurement"),
        manager_role_key="content_growth_planner",
        role_keys=("content_growth_planner", "market_intelligence_analyst", *specialist_role_keys("marketing-audience-growth")),
        decision_scope=("draft campaigns", "content calendars", "organic growth experiments"),
        success_measures=("qualified reach", "audience retention", "organic conversion", "content quality"),
        approval_boundaries=("Publishing, advertising spend, and public claims require owner approval.",),
    ),
    DepartmentSpec(
        key="revenue-partnerships", name="Revenue & Partnerships",
        mission="Prepare ethical sales and marketplace operations that convert validated demand into sustainable revenue.",
        accountabilities=("marketplace research", "listing preparation", "pricing analysis", "partner opportunity briefs"),
        manager_role_key="marketplace_operations_analyst",
        role_keys=("marketplace_operations_analyst", "financial_control_analyst", *specialist_role_keys("revenue-partnerships")),
        decision_scope=("draft listings", "analyse pricing", "prepare partner proposals"),
        success_measures=("qualified opportunity value", "listing readiness", "gross margin quality"),
        approval_boundaries=("No agent may publish, negotiate binding terms, change live prices, or commit to delivery without approval.",),
    ),
    DepartmentSpec(
        key="customer-operations", name="Customer Experience & Operations",
        mission="Make customer interactions, service delivery, and internal fulfilment accurate, consistent, and measurable.",
        accountabilities=("support triage", "customer knowledge", "fulfilment coordination", "service feedback"),
        manager_role_key="customer_experience_analyst",
        role_keys=("customer_experience_analyst", "marketplace_operations_analyst", *specialist_role_keys("customer-operations")),
        decision_scope=("classify issues", "prepare response drafts", "analyse service bottlenecks"),
        success_measures=("response-draft quality", "issue resolution time", "repeat issue rate", "fulfilment accuracy"),
        approval_boundaries=("Customer messages, refunds, and delivery commitments require owner approval.",),
    ),
    DepartmentSpec(
        key="finance-risk", name="Finance & Risk",
        mission="Protect financial discipline and identify operational, legal, privacy, and commercial exposure.",
        accountabilities=("cost tracking", "unit economics", "budget controls", "risk escalation"),
        manager_role_key="financial_control_analyst",
        role_keys=("financial_control_analyst", "risk_and_quality_reviewer", *specialist_role_keys("finance-risk")),
        decision_scope=("calculate scenarios", "reconcile owner-provided figures", "flag policy and cost risks"),
        success_measures=("cost forecast accuracy", "unapproved spend incidents", "risk closure time"),
        approval_boundaries=("Agents cannot move money, initiate payments, accept contracts, or change billing.",),
    ),
    DepartmentSpec(
        key="organizational-learning-quality", name="Organizational Learning & Quality",
        mission="Improve company performance through evidence, evaluation, incident learning, and independent review.",
        accountabilities=("agent evaluations", "quality reviews", "learning records", "improvement proposals"),
        manager_role_key="risk_and_quality_reviewer",
        role_keys=("risk_and_quality_reviewer", "software_engineering_lead", *specialist_role_keys("organizational-learning-quality")),
        decision_scope=("evaluate outputs", "recommend training and process changes", "open quality incidents"),
        success_measures=("evaluation coverage", "repeat defect rate", "improvement proposal success"),
        approval_boundaries=("No self-approval of high-impact changes; code modification and release retain separate controls.",),
    ),
))


def default_organization() -> OrganizationCatalog:
    return OPENCOMPANY_DEPARTMENTS
