"""Schemas for CEO-coordinated, durable company runs."""
from pydantic import BaseModel, Field

class RunStepCreate(BaseModel):
    step_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    agent_id: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=1, max_length=8000)
    context: str = Field(default="", max_length=12000)
    depends_on: list[str] = Field(default_factory=list, max_length=30)

class CompanyRunCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=8000)
    steps: list[RunStepCreate] = Field(min_length=1, max_length=50)

class StepReportCreate(BaseModel):
    status: str = Field(pattern=r"^(completed|blocked)$")
    summary: str = Field(min_length=1, max_length=8000)
    evidence: list[str] = Field(default_factory=list, max_length=50)
    blockers: list[str] = Field(default_factory=list, max_length=30)

class StepOut(BaseModel):
    step_key: str
    agent_id: str
    task: str
    context: str
    depends_on: list[str]
    status: str
    work_packet: dict | None = None
    report: dict | None = None
    created_at: str
    updated_at: str

class CompanyRunOut(BaseModel):
    id: str
    title: str
    description: str
    status: str
    created_at: str
    updated_at: str
    steps: list[StepOut]
    accountable_agent_id: str = "company-orchestrator"
