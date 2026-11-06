"""Input and output schemas for the CEO planning layer."""
from pydantic import BaseModel, Field

class CEOObjectiveCreate(BaseModel):
    objective: str = Field(min_length=8, max_length=2000)
    context: str = Field(default="", max_length=10000)
    constraints: str = Field(
        default="Zero budget and free resources first. Target international customers. No cold outreach. No publishing, external messages, spending, purchases, refunds, customer commitments, or production/security/financial changes without explicit owner approval requested by the CEO.",
        max_length=6000,
    )

class CEOPlanOut(BaseModel):
    run_id: str
    objective: str
    planning_mode: str
    accountable_agent_id: str
    selected_workstreams: list[str]
    decision_log: list[dict]
    run: dict
    limitations: list[str]
