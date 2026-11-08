"""API models."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

TaskStatus = Literal["queued", "running", "completed", "failed", "blocked"]
ApprovalStatus = Literal["pending", "approved", "rejected"]

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
    assigned_agent: str | None = None

class ApprovalCreate(BaseModel):
    task_id: str | None = None
    action: str = Field(min_length=1, max_length=120)
    details: str = Field(default="", max_length=5000)

class ApprovalOut(BaseModel):
    id: str
    task_id: str | None
    action: str
    details: str
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None = None

class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]


class AgentRegister(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=80)


class AgentOut(BaseModel):
    agent_id: str
    name: str
    role: str
    status: Literal["active", "paused"] 
    last_seen: datetime


class MemoryCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=10000)
    source: str = Field(default="", max_length=500)
    created_by: str = Field(min_length=1, max_length=100)


class MemoryOut(BaseModel):
    id: str
    key: str
    content: str
    source: str
    created_by: str
    created_at: datetime


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    actor_id: str
    entity_type: str
    entity_id: str
    payload: dict
    created_at: datetime
