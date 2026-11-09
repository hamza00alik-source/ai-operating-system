"""API models."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["queued", "running", "awaiting_approval", "completed", "failed", "blocked"]
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
    result: str | None = None
    error: str | None = None
    worker_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


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


class AuditEventOut(BaseModel):
    id: int
    event_type: str
    actor_id: str | None
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    created_at: datetime


class MCPServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    endpoint: str = Field(min_length=9, max_length=2048)
    credential_env: list[str] = Field(default_factory=list, max_length=20)
    declared_capabilities: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = False


class MCPServerOut(BaseModel):
    id: str
    name: str
    endpoint: str
    transport: Literal["streamable_http"]
    credential_env: list[str]
    declared_capabilities: list[str]
    enabled: bool
    connection_status: Literal["not_connected"]
    created_at: datetime
    updated_at: datetime



class MCPToolCall(BaseModel):
    tool_name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_id: str = Field(min_length=1, max_length=120)
    request_id: str | None = Field(default=None, max_length=120)


class MCPToolRequestCreate(BaseModel):
    server_id: str = Field(min_length=1, max_length=120)
    tool_name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = Field(default=None, max_length=120)


class MCPToolRequestOut(BaseModel):
    id: str
    task_id: str | None
    requester_id: str
    server_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: Literal["pending", "awaiting_approval", "approved", "rejected", "executed", "failed"]
    approval_id: str | None = None
    result: Any | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
