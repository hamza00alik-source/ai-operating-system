"""Core business entities and explicit lifecycle states."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(StrEnum):
    DISCOVERED = "discovered"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

class OpportunityStatus(StrEnum):
    NEW = "new"
    RESEARCHING = "researching"
    VALIDATED = "validated"
    REJECTED = "rejected"
    SELECTED = "selected"
    BUILDING = "building"
    LISTING_READY = "listing_ready"
    PUBLISHED = "published"
    SALE_CONFIRMED = "sale_confirmed"
    REVENUE_RECEIVED = "revenue_received"

@dataclass(frozen=True)
class Task:
    title: str
    objective: str
    department: str = "general"
    business_id: str = "company"
    id: UUID = field(default_factory=uuid4)
    status: TaskStatus = TaskStatus.DISCOVERED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    attempts: int = 0

@dataclass(frozen=True)
class Opportunity:
    name: str
    description: str
    demand_evidence: float
    buyer_access: float
    margin_potential: float
    ai_feasibility: float
    differentiation: float
    cost_risk: float
    id: UUID = field(default_factory=uuid4)
    status: OpportunityStatus = OpportunityStatus.NEW
    evidence_urls: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)

@dataclass(frozen=True)
class CompanyEvent:
    kind: str
    actor: str
    entity_type: str
    entity_id: str
    details: dict
    id: UUID = field(default_factory=uuid4)
    created_at: str = field(default_factory=utc_now)
