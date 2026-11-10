"""Persisted, owner-supervised department workflow templates and handoffs."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from ai_os.db import connect, initialize_database
from ai_os.brain import BUSINESS_IDS

TEMPLATES = {
    "digital-product-launch": {
        "name": "Digital product discovery to launch",
        "description": "A gated workflow for researching, specifying, producing, testing and preparing a downloadable digital product.",
        "steps": [
            ("research", "Validate customer demand and competitors", "Find evidence of real buyer demand, competitor offers, pricing signals and unresolved risks. Separate sourced facts from hypotheses. Do not invent market data."),
            ("product", "Write product requirements and acceptance criteria", "Turn approved research into a narrowly scoped product specification, target customer, user problem, deliverables, exclusions and measurable acceptance criteria."),
            ("design", "Create the design and production brief", "Prepare a detailed visual/asset specification, file formats, quality requirements and production checklist. Do not claim to have generated files."),
            ("engineering", "Prepare the implementation and packaging plan", "Define build steps, file structure, compatibility, dependencies, packaging and reproducibility. Do not claim code or binaries were produced."),
            ("testing", "Create QA and release test plan", "Create test cases for functionality, compatibility, usability, security, licensing and packaging. Identify release blockers."),
            ("finance", "Assess pricing, costs and unit economics", "Estimate costs only from explicit inputs; mark unknowns. Propose price hypotheses and a zero-spend validation route."),
            ("marketing", "Prepare marketplace listing draft", "Draft marketplace positioning, title, description, feature bullets, screenshots/assets checklist and keywords. Draft only; never publish or contact customers.")
        ]
    },
    "technology-evaluation": {
        "name": "Technology and API evaluation",
        "description": "A structured, evidence-led assessment before a tool or provider is adopted.",
        "steps": [
            ("research", "Collect primary-source evidence", "Identify official documentation, pricing, limits, licensing, privacy, retention, regions and current availability. Mark unverified fields."),
            ("engineering", "Assess integration feasibility", "Assess API compatibility, authentication, rate limits, deployment fit, failure modes and maintenance effort."),
            ("testing", "Design a safe validation test", "Specify a synthetic-data test, expected outcomes, failure checks and rollback. No credentials or live requests."),
            ("finance", "Review total cost and free-tier limits", "Identify explicit costs and uncertainty. No paid activation or spend."),
            ("operations", "Deliver adoption recommendation", "Summarize evidence, risks, owner decisions and a reversible next step. Do not enable integrations.")
        ]
    }
}

def initialize_workflows() -> None:
    initialize_database()
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS workflow_instances (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL DEFAULT 'core', template_id TEXT NOT NULL, name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflow_steps (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, task_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL, department TEXT NOT NULL, title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'blocked', created_at TEXT NOT NULL,
            UNIQUE(workflow_id, sequence_no), UNIQUE(task_id),
            FOREIGN KEY(workflow_id) REFERENCES workflow_instances(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow ON workflow_steps(workflow_id, sequence_no);
        """)

def list_templates() -> dict:
    return {"templates": [{"id": key, "name": value["name"], "description": value["description"],
        "step_count": len(value["steps"]), "departments": [s[0] for s in value["steps"]]}
        for key, value in TEMPLATES.items()],
        "execution_policy": "Only the first step is queued. Later steps remain blocked until the preceding step completes. Each step requires an explicit owner-triggered execution."}

def create_workflow(template_id: str, business_id: str = "core") -> dict:
    if business_id not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    if template_id not in TEMPLATES:
        raise LookupError("Workflow template not found")
    initialize_workflows()
    template = TEMPLATES[template_id]
    workflow_id, now = str(uuid4()), datetime.now(timezone.utc).isoformat()
    created = []
    with connect() as db:
        db.execute("INSERT INTO workflow_instances(id,business_id,template_id,name,status,created_at) VALUES(?,?,?,?,'active',?)",
                   (workflow_id, business_id, template_id, template["name"], now))
        for index, (department, title, description) in enumerate(template["steps"], start=1):
            task_id = str(uuid4())
            status = "queued" if index == 1 else "blocked"
            db.execute("""INSERT INTO tasks(id,title,description,department,business_id,status,created_at)
                VALUES(?,?,?,?,?,?,?)""", (task_id, title, description, department, business_id, status, now))
            step_id = str(uuid4())
            db.execute("""INSERT INTO workflow_steps
                (id,workflow_id,task_id,sequence_no,department,title,status,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (step_id, workflow_id, task_id, index, department, title, status, now))
            created.append({"id": step_id, "task_id": task_id, "sequence": index,
                            "department": department, "title": title, "status": status})
    return {"id": workflow_id, "template_id": template_id, "name": template["name"],
            "status": "active", "steps": created,
            "next_action": "Execute the first queued step from the Owner Console; subsequent steps unlock only after completion."}

def get_workflow(workflow_id: str) -> dict | None:
    initialize_workflows()
    with connect() as db:
        workflow = db.execute("SELECT * FROM workflow_instances WHERE id=?", (workflow_id,)).fetchone()
        if not workflow:
            return None
        steps = db.execute("SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY sequence_no", (workflow_id,)).fetchall()
    return {**dict(workflow), "steps": [dict(step) for step in steps]}

def task_is_runnable(task_id: str) -> bool:
    initialize_workflows()
    with connect() as db:
        step = db.execute("SELECT * FROM workflow_steps WHERE task_id=?", (task_id,)).fetchone()
        if not step:
            return True
        return step["status"] == "queued"

def finish_workflow_task(task_id: str, success: bool) -> None:
    initialize_workflows()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        step = db.execute("SELECT * FROM workflow_steps WHERE task_id=?", (task_id,)).fetchone()
        if not step:
            return
        if not success:
            db.execute("UPDATE workflow_steps SET status='failed' WHERE task_id=?", (task_id,))
            db.execute("UPDATE workflow_instances SET status='blocked' WHERE id=?", (step["workflow_id"],))
            return
        db.execute("UPDATE workflow_steps SET status='completed' WHERE task_id=?", (task_id,))
        following = db.execute("""SELECT * FROM workflow_steps WHERE workflow_id=? AND sequence_no=?
            AND status='blocked'""", (step["workflow_id"], step["sequence_no"] + 1)).fetchone()
        if following:
            db.execute("UPDATE workflow_steps SET status='queued' WHERE id=?", (following["id"],))
            db.execute("UPDATE tasks SET status='queued' WHERE id=?", (following["task_id"],))
        else:
            db.execute("UPDATE workflow_instances SET status='completed' WHERE id=?", (step["workflow_id"],))

def list_workflows(limit: int = 50, business_id: str = "core") -> list[dict]:
    if business_id not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    initialize_workflows()
    with connect() as db:
        rows = db.execute("SELECT id FROM workflow_instances WHERE business_id=? ORDER BY created_at DESC LIMIT ?", (business_id, max(1, min(limit, 100)))).fetchall()
    return [item for row in rows if (item := get_workflow(row["id"])) is not None]
