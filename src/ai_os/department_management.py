"""Department manager workload and CEO company-wide coordination views.

This layer derives truthful workload from durable company runs and queue records.
It does not create independent processes or grant department managers authority.
"""
from collections import Counter

from ai_os.departments import get_department, list_departments
from ai_os.execution import list_company_runs
from ai_os.queue import list_jobs
from ai_os.registry import get_agent, list_agents
from ai_os.department_coordination import list_department_plans_for_runs


def _department_agent_ids(department: dict) -> set[str]:
    manager = get_agent(department["manager_agent_id"])
    if manager is None:
        return set()
    return {
        agent.id for agent in list_agents()
        if agent.department == manager.department
    } | {manager.id}


def get_department_workload(department_id: str, *, run_limit: int = 200) -> dict | None:
    department = get_department(department_id)
    if department is None:
        return None
    manager = get_agent(department["manager_agent_id"])
    member_ids = _department_agent_ids(department)
    runs = list_company_runs(limit=run_limit)
    jobs = list_jobs(limit=500)
    job_by_step = {}
    for job in jobs:
        payload = job.get("payload") or {}
        if job.get("job_type") == "execute_company_step":
            job_by_step[(payload.get("run_id"), payload.get("step_key"))] = {
                "id": job["id"], "status": job["status"],
                "attempts": job["attempts"], "error": job.get("error"),
            }

    manager_plans = [plan for plan in list_department_plans_for_runs([run["id"] for run in runs])
                     if plan["department_id"] == department_id]
    plan_counts = Counter(plan["status"] for plan in manager_plans)
    steps = []
    for run in runs:
        for step in run.get("steps", []):
            if step.get("agent_id") not in member_ids:
                continue
            steps.append({
                "run_id": run["id"], "run_title": run["title"],
                "step_key": step["step_key"], "agent_id": step["agent_id"],
                "status": step["status"], "depends_on": step["depends_on"],
                "updated_at": step["updated_at"],
                "report": step.get("report"),
                "job": job_by_step.get((run["id"], step["step_key"])),
            })
    counts = Counter(item["status"] for item in steps)
    return {
        "id": department["id"],
        "name": department["name"],
        "mission": department["mission"],
        "manager": ({"id": manager.id, "name": manager.name} if manager else None),
        "manager_available": bool(manager and manager.enabled),
        "manager_profile_department": manager.department if manager else None,
        "specialist_count": len(member_ids),
        "workload": {
            "total": len(steps),
            "pending": counts.get("pending", 0),
            "assigned": counts.get("assigned", 0),
            "completed": counts.get("completed", 0),
            "blocked": counts.get("blocked", 0),
        },
        "items": sorted(steps, key=lambda item: item["updated_at"], reverse=True)[:50],
        "manager_coordination": {
            "plans_total": len(manager_plans),
            "delegated": plan_counts.get("delegated", 0),
            "reviewed": plan_counts.get("reviewed", 0),
            "blocked": plan_counts.get("blocked", 0),
            "items": manager_plans[:10],
        },
        "execution_enabled": False,
        "notice": (
            "Workload is derived from existing company-run steps assigned to the "
            "manager profile's source division. No separate manager process exists."
        ),
    }


def get_company_overview(*, run_limit: int = 200) -> dict:
    departments = [
        get_department_workload(item["id"], run_limit=run_limit)
        for item in list_departments()
    ]
    totals = Counter()
    for item in departments:
        if item is None:
            continue
        totals.update(item["workload"])
    runs = list_company_runs(limit=run_limit)
    run_counts = Counter(run["status"] for run in runs)
    return {
        "accountable_agent_id": "company-orchestrator",
        "department_count": len(departments),
        "departments": departments,
        "company_workload": {
            "total_department_assignments": totals.get("total", 0),
            "pending": totals.get("pending", 0),
            "assigned": totals.get("assigned", 0),
            "completed": totals.get("completed", 0),
            "blocked": totals.get("blocked", 0),
        },
        "manager_coordination": {
            "plans_total": sum(item.get("manager_coordination", {}).get("plans_total", 0) for item in departments if item),
            "delegated": sum(item.get("manager_coordination", {}).get("delegated", 0) for item in departments if item),
            "reviewed": sum(item.get("manager_coordination", {}).get("reviewed", 0) for item in departments if item),
            "blocked": sum(item.get("manager_coordination", {}).get("blocked", 0) for item in departments if item),
        },
        "company_runs": {
            "total": len(runs),
            "queued": run_counts.get("queued", 0),
            "running": run_counts.get("running", 0),
            "completed": run_counts.get("completed", 0),
            "blocked": run_counts.get("blocked", 0),
        },
        "governance": {
            "department_managers_can_approve_external_actions": False,
            "owner_approval_required_for_sensitive_actions": True,
            "autonomous_department_execution_enabled": False,
        },
    }
