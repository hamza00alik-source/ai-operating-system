"""CEO-controlled selection and delegation to department managers.

This endpoint is explicitly invoked by the owner. It uses only departments whose
manager profile was selected by the deterministic CEO plan. Each manager plan
uses the configured model adapter; no provider is contacted by CEO planning alone.
"""
from ai_os.departments import list_departments
from ai_os.department_coordination import create_department_plan
from ai_os.execution import get_company_run

CEO_AGENT_ID = "company-orchestrator"


def delegate_ceo_selected_departments(run_id: str) -> dict:
    run = get_company_run(run_id)
    if run is None:
        raise LookupError("Company run not found")

    assigned_agent_ids = {
        step["agent_id"] for step in run["steps"]
        if step.get("agent_id") and step.get("agent_id") != CEO_AGENT_ID
    }
    selected = [
        department for department in list_departments()
        if department["manager_agent_id"] in assigned_agent_ids
    ]
    if not selected:
        return {
            "run_id": run_id,
            "accountable_agent_id": CEO_AGENT_ID,
            "selected_departments": [],
            "delegations": [],
            "notice": "The CEO plan did not assign any department-manager profiles; no manager model calls were made.",
        }

    delegations = []
    for department in selected:
        result = create_department_plan(run_id, department["id"])
        delegations.append({
            "department_id": department["id"],
            "department_name": department["name"],
            "manager_agent_id": department["manager_agent_id"],
            "status": result["status"],
            "reused_existing_plan": result.get("reused_existing_plan", False),
            "plan_id": result.get("id") or result.get("plan_id"),
            "task_count": len((result.get("plan") or {}).get("tasks", [])),
        })

    return {
        "run_id": run_id,
        "accountable_agent_id": CEO_AGENT_ID,
        "selected_departments": [item["id"] for item in selected],
        "delegations": delegations,
        "notice": "CEO-selected department managers created durable internal specialist assignments. Worker dispatch remains controlled by the shared runtime; external actions remain disabled.",
    }
