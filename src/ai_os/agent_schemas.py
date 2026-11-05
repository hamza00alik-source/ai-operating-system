"""Response models for agent discovery and deterministic plans."""
from pydantic import BaseModel

class AgentOut(BaseModel):
    id: str
    name: str
    department: str
    description: str
    capabilities: list[str]
    requires_approval_for: list[str]
    enabled: bool

class PlanCreate(BaseModel):
    title: str
    description: str = ""
    department: str

class PlanOut(BaseModel):
    plan_id: str
    title: str
    department: str
    assigned_agent: dict[str, str]
    status: str
    execution_enabled: bool
    steps: list[dict]
    approval_gates: list[str]
    description: str
    notice: str
