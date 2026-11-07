"""Request and response models for CEO governance policy evaluation."""
from pydantic import BaseModel, Field

class GovernanceEvaluateIn(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=120)

class GovernanceEvaluateOut(BaseModel):
    decision: str
    allowed: bool
    owner_approval_required: bool
    accountable_agent_id: str
    reason: str
