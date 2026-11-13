"""Request schemas for the standalone OpenCompany API.

Keep validation constraints and defaults here so route modules can import
stable request contracts without coupling to the API composition root.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from opencompany_core.domain import AgentState, TaskState
from opencompany_core.learning import OutcomeGrade


class OwnerLoginInput(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)

class UnoRouterSettingsInput(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    model: str = Field(min_length=3, max_length=200, pattern=r"^[A-Za-z0-9._/-]+:free$")
    confirm_free: bool

class UnoRouterDiscoveryInput(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)

class GitHubEvolutionSettingsInput(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    confirm_draft_pr_only: bool

class VentureOpportunityInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    business_model: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=5000)
    target_market: str = Field(min_length=1, max_length=300)
    evidence: list[dict] = Field(default_factory=list, max_length=20)

class VentureOpportunityStatusInput(BaseModel):
    status: str = Field(min_length=1, max_length=40)
    rationale: str = Field(default="", max_length=2000)
    confirm_owner_approval: bool = False

class PlanItemInput(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=12000)
    department: str = Field(min_length=1, max_length=80)
    state: TaskState = TaskState.READY
    depends_on: tuple[UUID, ...] = ()
    business_id: str = "core"

class PlanPreviewInput(BaseModel):
    items: list[PlanItemInput] = Field(max_length=200)

class WorkforceRoutePreviewInput(BaseModel):
    department: str = Field(min_length=1, max_length=80)
    required_capabilities: list[str] = Field(min_length=1, max_length=20)
    limit: int = Field(default=5, ge=1, le=10)

class AgentStateChangeInput(BaseModel):
    target_state: AgentState
    expected_revision: int = Field(ge=1)

class WorkItemCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=12000)
    department: str = Field(min_length=1, max_length=80)
    depends_on: tuple[UUID, ...] = ()
    business_id: str = "core"

class CommercialOpportunityInput(BaseModel):
    business_id: str
    customer_name: str = Field(min_length=1, max_length=200)
    customer_contact: str | None = Field(default=None, max_length=320)
    customer_need: str = Field(min_length=1, max_length=4000)
    scope_confirmed: bool

class CommercialProductStatusInput(BaseModel):
    status: str
    confirm_owner_approval: bool

class CommercialProductInput(BaseModel):
    business_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=120)

class CommercialQuoteLineInput(BaseModel):
    product_id: UUID
    description: str = Field(min_length=1, max_length=500)
    quantity: int = Field(ge=1, le=10000)
    unit_price_minor: int = Field(ge=1, le=9_000_000_000_000_000)

class CommercialQuoteInput(BaseModel):
    opportunity_id: UUID
    title: str = Field(min_length=1, max_length=200)
    currency: str = Field(min_length=3, max_length=3)
    currency_exponent: int = Field(default=2)
    terms: str = Field(min_length=1, max_length=4000)
    items: list[CommercialQuoteLineInput] = Field(min_length=1, max_length=100)

class CommercialQuoteDecisionInput(BaseModel):
    status: str
    confirm_owner_decision: bool
    acceptance_reference: str | None = Field(default=None, max_length=1000)

class CommercialOrderStatusInput(BaseModel):
    status: str
    confirm_owner_status: bool

class CommercialOrderInput(BaseModel):
    quote_id: UUID
    confirm_owner_order_record: bool

class DelegationPreviewInput(BaseModel):
    required_capabilities: list[str] = Field(min_length=1, max_length=20)
    max_specialists: int = Field(default=15, ge=1, le=50)

class ApiAnythingCallInput(BaseModel):
    site: str = Field(min_length=1, max_length=80)
    operation: str = Field(min_length=1, max_length=100)
    args: dict = Field(default_factory=dict)
    max_age_ms: int = Field(default=0, ge=0, le=86400000)

class ApiAnythingBatchInput(BaseModel):
    calls: list[dict] = Field(min_length=1, max_length=20)

class CodeEvolutionInput(BaseModel):
    problem: str = Field(min_length=1, max_length=3000)
    file_paths: list[str] = Field(min_length=1, max_length=3)

class OutcomeEvaluationInput(BaseModel):
    grade: OutcomeGrade
    rubric_scores: dict[str, int] = Field(min_length=1, max_length=20)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)
    observations: str = Field(min_length=1, max_length=6000)

class LearningAIProposalInput(BaseModel):
    evaluation_ids: list[UUID] = Field(min_length=1, max_length=5)

class ImprovementProposalInput(BaseModel):
    target: str = Field(min_length=1, max_length=2000)
    change_summary: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)
    expected_measurement: str = Field(min_length=1, max_length=2000)
    risk_level: str = Field(min_length=1, max_length=80)
    based_on_evaluations: list[UUID] = Field(min_length=1, max_length=20)

class LearningDecisionInput(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)

class LearningNoteInput(BaseModel):
    role_key: str = Field(min_length=1, max_length=160)
    note: str = Field(min_length=1, max_length=3000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)
    business_id: str = "core"

class HandoffCreateInput(BaseModel):
    recipient_agent_id: UUID
    purpose: str = Field(min_length=1, max_length=240)
    requested_result: str = Field(min_length=1, max_length=1200)
    context: str = Field(min_length=1, max_length=6000)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=20)

class HandoffDeliverInput(BaseModel):
    response_artifact_ids: list[UUID] = Field(min_length=1, max_length=20)

class ExecutivePlanInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=12000)
    max_tasks: int = Field(default=8, ge=1, le=10)
    business_id: str = "core"

class ManagerProposalInput(BaseModel):
    max_specialists: int = Field(default=15, ge=1, le=50)

class WorkItemTransitionInput(BaseModel):
    target_state: TaskState

class WorkItemReviewInput(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)

class CommercialSupplierInput(BaseModel):
    business_id: str
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=100)
    product_categories: list[str] = Field(default_factory=list, max_length=30)
    notes: str = Field(default="", max_length=3000)

class CommercialSupplierStatusInput(BaseModel):
    status: str
    confirm_owner_decision: bool

class CommercialFinancialEventInput(BaseModel):
    business_id: str
    order_id: UUID | None = None
    event_type: str = Field(min_length=1, max_length=40)
    amount_minor: int = Field(gt=0, le=9_000_000_000_000_000)
    currency: str = Field(min_length=3, max_length=3)
    source_reference: str = Field(min_length=1, max_length=200)
    evidence_reference: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=2000)
    occurred_at: datetime
    owner_verified: bool

