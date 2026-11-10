"""Original OpenCompany domain contracts.

This module defines business concepts and invariants only. It performs no I/O,
model calls, scheduling, or external actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID


def _require_text(value: str, field_name: str, *, maximum: int = 500) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")


def _require_utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{field_name} must be expressed in UTC")


class AgentState(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class TaskState(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    BLOCKED = "blocked"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class AgentProfile:
    id: UUID
    name: str
    department: str
    purpose: str
    capabilities: tuple[str, ...]
    state: AgentState = AgentState.DRAFT
    revision: int = 1

    def __post_init__(self) -> None:
        _require_text(self.name, "name", maximum=120)
        _require_text(self.department, "department", maximum=80)
        _require_text(self.purpose, "purpose", maximum=2000)
        if self.revision < 1:
            raise ValueError("revision must be positive")
        if not self.capabilities or any(not item.strip() for item in self.capabilities):
            raise ValueError("capabilities must contain non-empty entries")


@dataclass(frozen=True, slots=True)
class WorkItem:
    id: UUID
    title: str
    objective: str
    department: str
    state: TaskState = TaskState.DRAFT
    assigned_agent_id: UUID | None = None
    depends_on: tuple[UUID, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _require_text(self.title, "title", maximum=240)
        _require_text(self.objective, "objective", maximum=12000)
        _require_text(self.department, "department", maximum=80)
        _require_utc(self.created_at, "created_at")
        if self.id in self.depends_on:
            raise ValueError("a work item cannot depend on itself")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("dependency identifiers must be unique")


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    id: UUID
    work_item_id: UUID
    sequence: int
    state: AttemptState
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        if self.started_at is not None:
            _require_utc(self.started_at, "started_at")
        if self.finished_at is not None:
            _require_utc(self.finished_at, "finished_at")
        if self.finished_at and not self.started_at:
            raise ValueError("finished attempts must have a start time")
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        if self.state == AttemptState.RUNNING and not self.started_at:
            raise ValueError("running attempts require started_at")
        if self.state in {AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.CANCELLED}:
            if not self.finished_at:
                raise ValueError("terminal attempts require finished_at")
        if self.state == AttemptState.FAILED and not self.failure_code:
            raise ValueError("failed attempts require a failure_code")


@dataclass(frozen=True, slots=True)
class WorkArtifact:
    id: UUID
    work_item_id: UUID
    name: str
    media_type: str
    locator: str
    created_by_agent_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.name, "name", maximum=240)
        _require_text(self.media_type, "media_type", maximum=160)
        _require_text(self.locator, "locator", maximum=2000)
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    id: UUID
    action: str
    target_type: str
    target_id: str
    requested_by: str
    state: ApprovalState = ApprovalState.PENDING
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
    decided_by: str | None = None
    rationale: str | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("action", "target_type", "target_id", "requested_by"):
            _require_text(getattr(self, field_name), field_name, maximum=240)
        _require_utc(self.requested_at, "requested_at")
        if self.decided_at is not None:
            _require_utc(self.decided_at, "decided_at")
        if self.expires_at is not None:
            _require_utc(self.expires_at, "expires_at")
        if self.state == ApprovalState.PENDING and self.decided_at is not None:
            raise ValueError("pending approvals cannot have a decision timestamp")
        if self.state in {ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.WITHDRAWN}:
            if self.decided_at is None or not self.decided_by:
                raise ValueError("decided approvals require decided_at and decided_by")
        if self.state == ApprovalState.EXPIRED and self.decided_at is None:
            raise ValueError("expired approvals require a recorded expiry time")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: str
    action: str
    subject_type: str
    subject_id: str
    outcome: str
    correlation_id: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_utc(self.occurred_at, "occurred_at")
        for field_name in ("actor_type", "actor_id", "action", "subject_type",
                           "subject_id", "outcome", "correlation_id"):
            _require_text(getattr(self, field_name), field_name, maximum=240)
