"""Deterministic planning primitives; this module does not call an LLM or tools."""
from uuid import uuid4
from ai_os.registry import select_agent

APPROVAL_REQUIRED_ACTIONS = {
    "publishing", "spending", "customer_commitment", "external_message",
    "refund", "production_change", "paid_promotion",
}

def build_plan(title: str, description: str, department: str) -> dict:
    agent = select_agent(department)
    if agent is None:
        raise LookupError(f"No enabled agent is registered for department '{department}'")
    gates = sorted(set(agent.requires_approval_for).intersection(APPROVAL_REQUIRED_ACTIONS))
    return {
        "plan_id": str(uuid4()),
        "title": title,
        "department": department,
        "assigned_agent": {"id": agent.id, "name": agent.name},
        "status": "planned",
        "execution_enabled": False,
        "steps": [
            {"number": 1, "name": "Review task and available context", "status": "not_started"},
            {"number": 2, "name": "Prepare work and evidence", "status": "not_started"},
            {"number": 3, "name": "Return output for review", "status": "not_started"}
        ],
        "approval_gates": gates,
        "description": description,
        "notice": "Planning only. No model, external tool, publishing, spending, or customer action was executed."
    }
