"""Durable department-manager delegation and review contracts.

A manager plan is a bounded model-assisted internal workflow. It creates queued
specialist steps but does not start workers or permit external actions.
"""
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.departments import get_department
from ai_os.execution import get_company_run
from ai_os.model_adapter import generate_json
from ai_os.registry import get_agent, list_agents, load_agent_profile

CEO_AGENT_ID = "company-orchestrator"
MAX_TASKS = 8
_STEP_KEY = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(row) -> dict:
    item = dict(row)
    item["plan"] = json.loads(item.pop("plan_json"))
    item["review"] = json.loads(item.pop("review_json")) if item.get("review_json") else None
    return item


def get_department_plan(run_id: str, department_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM department_manager_plans WHERE run_id=? AND department_id=?",
            (run_id, department_id),
        ).fetchone()
    return _decode(row) if row else None


def list_department_plans(run_id: str) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM department_manager_plans WHERE run_id=? ORDER BY created_at, department_id",
            (run_id,),
        ).fetchall()
    return [_decode(row) for row in rows]


def _manager_context(department_id: str):
    department = get_department(department_id)
    if department is None:
        raise LookupError("Department not found")
    manager = get_agent(department["manager_agent_id"])
    if manager is None or not manager.enabled or manager.id == CEO_AGENT_ID:
        raise ValueError("Department manager profile is unavailable or disabled")
    profile = load_agent_profile(manager.id)
    if not profile.strip():
        raise ValueError("Department manager profile content is unavailable")
    members = [
        agent for agent in list_agents()
        if agent.enabled and agent.id != manager.id and agent.department == manager.department
    ]
    if not members:
        raise ValueError("No enabled specialist profiles are available in the manager's source division")
    return department, manager, profile, members


def create_department_plan(run_id: str, department_id: str) -> dict:
    """Ask a configured model to create a bounded specialist delegation plan."""
    run = get_company_run(run_id)
    if run is None:
        raise LookupError("Company run not found")
    existing = get_department_plan(run_id, department_id)
    if existing is not None:
        return {**existing, "reused_existing_plan": True}

    department, manager, profile, members = _manager_context(department_id)
    existing_keys = {step["step_key"] for step in run["steps"]}
    member_options = [
        {"id": agent.id, "name": agent.name, "expertise": agent.description[:500]}
        for agent in members[:80]
    ]
    system_prompt = f"""You are {manager.name}, the department manager for {department['name']}.
Use the imported Agency Agents role profile below as workflow guidance only.
<manager_profile>
{profile[:24000]}
</manager_profile>
You receive objectives from the company CEO. Break the objective into at most {MAX_TASKS}
small, independently executable internal specialist tasks. Assign only agents from the
provided eligible specialist list. Do not assign yourself or the CEO. Do not invent agent IDs.
Tasks must be internal research, analysis, drafting, planning, or quality work only.
Never publish, send messages, spend, purchase, issue refunds, make customer commitments,
change production, access accounts, or request owner approval. Those actions are outside
your authority and must be escalated to the CEO.
Return only JSON: {{"tasks":[{{"step_key":"short_unique_key","agent_id":"eligible-id",
"task":"specific task","context":"optional context","depends_on":["other_key"]}}]}}.
"""
    user_prompt = json.dumps({
        "company_run_id": run_id,
        "company_objective": run["title"],
        "company_context": run["description"],
        "department": {
            "id": department_id, "name": department["name"],
            "mission": department["mission"], "workstreams": department["workstreams"],
            "approval_gates": department["approval_gates"],
        },
        "eligible_specialists": member_options,
        "existing_step_keys": sorted(existing_keys),
        "instructions": "Delegate concrete tasks aligned with this department's mission. Avoid duplicating existing steps.",
    }, ensure_ascii=False)
    raw, provider = generate_json(system_prompt, user_prompt)
    tasks = raw.get("tasks") if isinstance(raw, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
        raise ValueError(f"Department manager must return between 1 and {MAX_TASKS} tasks")

    eligible = {agent.id: agent for agent in members}
    normalized = []
    keys = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("Every manager task must be an object")
        key, agent_id = task.get("step_key"), task.get("agent_id")
        description = task.get("task")
        context = task.get("context", "")
        dependencies = task.get("depends_on", [])
        if not isinstance(key, str) or not _STEP_KEY.fullmatch(key):
            raise ValueError("Manager task step_key is invalid")
        if key in existing_keys or key in keys:
            raise ValueError("Manager task step_key duplicates an existing or proposed step")
        if not isinstance(agent_id, str) or agent_id not in eligible:
            raise ValueError("Manager may assign only enabled specialists in its source division")
        if not isinstance(description, str) or not description.strip() or len(description) > 8000:
            raise ValueError("Manager task must contain a non-empty description up to 8000 characters")
        if not isinstance(context, str) or len(context) > 12000:
            raise ValueError("Manager task context must be text up to 12000 characters")
        if not isinstance(dependencies, list) or len(dependencies) > MAX_TASKS:
            raise ValueError("Manager task dependencies must be a bounded list")
        keys.add(key)
        normalized.append({
            "step_key": key, "agent_id": agent_id, "task": description.strip(),
            "context": context.strip(), "depends_on": dependencies,
        })

    graph = {item["step_key"]: item["depends_on"] for item in normalized}
    for key, dependencies in graph.items():
        if len(dependencies) != len(set(dependencies)) or any(dep not in keys or dep == key for dep in dependencies):
            raise ValueError(f"Manager task {key} has invalid dependencies")
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError("Department manager plan dependencies must be acyclic")
        if key in visited:
            return
        visiting.add(key)
        for dependency in graph[key]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
    for key in graph:
        visit(key)

    plan_id, now = str(uuid4()), _now()
    plan = {
        "plan_id": plan_id, "department_id": department_id,
        "department_name": department["name"], "manager_agent_id": manager.id,
        "manager_name": manager.name, "tasks": normalized,
        "provider": provider.get("provider"), "model": provider.get("model"),
    }
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Re-check uniqueness inside the write transaction.
        prior = db.execute(
            "SELECT * FROM department_manager_plans WHERE run_id=? AND department_id=?",
            (run_id, department_id),
        ).fetchone()
        if prior:
            return {**_decode(prior), "reused_existing_plan": True}
        position = db.execute(
            "SELECT COALESCE(MAX(position),-1)+1 AS next_position FROM company_run_steps WHERE run_id=?",
            (run_id,),
        ).fetchone()["next_position"]
        for task in normalized:
            db.execute(
                """INSERT INTO company_run_steps
                (run_id,step_key,agent_id,task,context,depends_on_json,status,position,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'pending',?,?,?)""",
                (run_id, task["step_key"], task["agent_id"], task["task"], task["context"],
                 json.dumps(task["depends_on"]), position, now, now),
            )
            position += 1
        db.execute(
            """INSERT INTO department_manager_plans
            (id,run_id,department_id,manager_agent_id,status,plan_json,review_json,provider,model,created_at,updated_at)
            VALUES(?,?,?,?,'delegated',?,NULL,?,?,?,?)""",
            (plan_id, run_id, department_id, manager.id,
             json.dumps(plan, separators=(",", ":"), ensure_ascii=False),
             provider.get("provider", "unknown"), provider.get("model", "unknown"), now, now),
        )
        db.execute("UPDATE company_runs SET status='queued',updated_at=? WHERE id=?", (now, run_id))
    return {
        "id": plan_id, "run_id": run_id, "department_id": department_id,
        "manager_agent_id": manager.id, "status": "delegated", "plan": plan,
        "review": None, "created_at": now, "updated_at": now,
        "reused_existing_plan": False,
        "notice": "Specialist tasks are durably queued. They are not dispatched until the shared worker runtime is enabled.",
    }


def review_department_plan(run_id: str, department_id: str) -> dict:
    """Manager reviews all delegated specialist reports and records a CEO-facing summary."""
    plan = get_department_plan(run_id, department_id)
    if plan is None:
        raise LookupError("Department manager plan not found")
    if plan["review"] is not None:
        return {**plan, "reused_existing_review": True}
    run = get_company_run(run_id)
    if run is None:
        raise LookupError("Company run not found")
    tasks = plan["plan"]["tasks"]
    step_by_key = {step["step_key"]: step for step in run["steps"]}
    reports = []
    for task in tasks:
        step = step_by_key.get(task["step_key"])
        if step is None or step["status"] not in {"completed", "blocked"}:
            raise ValueError("Department manager can review only after every delegated task is completed or blocked")
        reports.append({
            "step_key": step["step_key"], "agent_id": step["agent_id"],
            "task": step["task"], "status": step["status"], "report": step.get("report"),
        })
    department, manager, profile, _ = _manager_context(department_id)
    system_prompt = f"""You are {manager.name}, reviewing work as the manager of {department['name']}.
Use this role profile as expertise guidance only:
<manager_profile>
{profile[:24000]}
</manager_profile>
Assess the delegated specialist reports for completeness, evidence quality, relevance,
risks, and blockers. Report to the company CEO. Do not approve external actions, publish,
send messages, spend, make commitments, or claim execution beyond the supplied reports.
Return only JSON with keys: status (reviewed or blocked), summary (string),
quality_findings (array), blockers (array), recommendations_for_ceo (array),
needs_ceo_attention (boolean).
"""
    raw, provider = generate_json(system_prompt, json.dumps({
        "company_objective": run["title"], "department": department["name"],
        "manager_plan": plan["plan"], "specialist_reports": reports,
    }, ensure_ascii=False))
    if not isinstance(raw, dict) or raw.get("status") not in {"reviewed", "blocked"}:
        raise ValueError("Department manager returned an invalid review status")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Department manager review must include a summary")
    review = {
        "status": raw["status"], "summary": summary.strip()[:8000],
        "quality_findings": raw.get("quality_findings", [])[:20] if isinstance(raw.get("quality_findings", []), list) else [],
        "blockers": raw.get("blockers", [])[:20] if isinstance(raw.get("blockers", []), list) else [],
        "recommendations_for_ceo": raw.get("recommendations_for_ceo", [])[:20] if isinstance(raw.get("recommendations_for_ceo", []), list) else [],
        "needs_ceo_attention": bool(raw.get("needs_ceo_attention", False)),
        "reviewed_by": manager.id, "provider": provider.get("provider"), "model": provider.get("model"),
    }
    now = _now()
    with connect() as db:
        db.execute(
            """UPDATE department_manager_plans SET status=?,review_json=?,provider=?,model=?,updated_at=?
               WHERE run_id=? AND department_id=? AND review_json IS NULL""",
            (raw["status"], json.dumps(review, separators=(",", ":"), ensure_ascii=False),
             provider.get("provider", "unknown"), provider.get("model", "unknown"),
             now, run_id, department_id),
        )
    return {**get_department_plan(run_id, department_id), "reused_existing_review": False}


def list_department_plans_for_runs(run_ids: list[str]) -> list[dict]:
    """Load manager plans for a bounded set of company runs in one query."""
    if not run_ids:
        return []
    ids = list(dict.fromkeys(run_ids))[:500]
    placeholders = ",".join("?" for _ in ids)
    with connect() as db:
        rows = db.execute(
            f"SELECT * FROM department_manager_plans WHERE run_id IN ({placeholders}) ORDER BY created_at DESC",
            ids,
        ).fetchall()
    return [_decode(row) for row in rows]
