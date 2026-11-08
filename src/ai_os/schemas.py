"""API models."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["queued", "running", "completed", "failed", "blocked"]
ApprovalStatus = Literal["pending", "approved", "rejected", "consumed", "expired"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    department: str = Field(default="general", min_length=1, max_length=80)


class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    department: str
    status: TaskStatus
    created_at: datetime


class ApprovalCreate(BaseModel):
    task_id: str | None = None
    action: str = Field(min_length=1, max_length=120)
    details: str = Field(default="", max_length=5000)
    actor_id: str = Field(min_length=1, max_length=120)
    resource_id: str = Field(min_length=1, max_length=240)
    action_payload: dict[str, Any]
    expires_in_seconds: int = Field(default=900, ge=60, le=604800)


class ApprovalOut(BaseModel):
    id: str
    task_id: str | None
    action: str
    details: str
    actor_id: str | None = None
    resource_id: str | None = None
    action_payload: dict[str, Any] | None = None
    action_fingerprint: str | None = None
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    consumed_at: datetime | None = None


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
