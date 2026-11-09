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


class DiscoveryScanCreate(BaseModel):
    categories: list[Literal["agent-frameworks", "mcp-servers", "rag-storage", "self-hosted", "llm-tools"]] = Field(min_length=1, max_length=5)


class CandidateReviewDecision(BaseModel):
    repository_url: str = Field(min_length=12, max_length=500)
    decision: Literal["approved-for-sandbox", "rejected"]
    notes: str = Field(default="", max_length=2000)



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


class MCPServerEnable(BaseModel):
    enabled: bool
