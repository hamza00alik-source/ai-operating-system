"""Schemas for department manager coordination endpoints."""
from pydantic import BaseModel

class DepartmentPlanOut(BaseModel):
    id: str
    run_id: str
    department_id: str
    manager_agent_id: str
    status: str
    plan: dict
    review: dict | None = None
    created_at: str
    updated_at: str
