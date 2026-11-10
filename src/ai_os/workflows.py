"""Persisted, owner-supervised department workflow templates and handoffs."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
import json
from ai_os.db import connect, initialize_database
from ai_os.brain import BUSINESS_IDS
from ai_os.workflow_dag import COMPANY_CYCLE_DEPENDENCIES

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
    ,
    "company-wide-operating-cycle": {
        "name": "Company-wide cross-department operating cycle",
        "description": "A supervised end-to-end cycle for one objective in exactly one business environment. Business records and customer data must never be mixed.",
        "steps": [
            ("executive", "Set objective, scope and owner decision gates", "Define the objective, selected business environment, measurable outcome, exclusions, risks and owner approval gates. Keep the physical-products agency, own physical-products brand and digital-products business separate."),
            ("research", "Validate the opportunity with evidence", "Collect dated, attributable evidence about customers, demand, competitors, market conditions and risks. Separate verified facts, estimates and hypotheses; cite primary sources and mark unknowns."),
            ("product", "Specify the offer and acceptance criteria", "Define the proposed offer, target buyer, value proposition, deliverables, exclusions, acceptance criteria and assumptions. Do not promise availability or delivery."),
            ("design", "Prepare creative and production specifications", "Produce a detailed creative brief, visual direction, required assets, file formats and quality criteria. Distinguish a brief from assets actually created."),
            ("engineering", "Assess technical delivery and integrations", "Define implementation tasks, dependencies, architecture, security, data handling and integration requirements. Prefer free/read-only options; do not connect accounts or deploy."),
            ("legal-compliance", "Review licensing, platform and policy risks", "Identify applicable platform terms, intellectual-property/licensing concerns, privacy and advertising-claim risks. Cite authoritative sources and flag matters needing qualified legal review."),
            ("quality-assurance", "Verify deliverables and release readiness", "Create and execute only available safe tests; record test evidence, defects, compatibility, acceptance status and release blockers. Never mark untested work as passed."),
            ("marketing", "Prepare audience and campaign materials", "Develop positioning, channel strategy, content calendar, SEO/marketplace keywords and draft creative copy. Draft only; no publishing, paid promotion or customer outreach."),
            ("sales-marketplace", "Prepare inbound sales and listing operations", "Prepare listing drafts, pricing hypotheses, marketplace requirements, enquiry qualification and order handoff procedures. Do not publish, accept orders or make customer commitments."),
            ("customer-support", "Prepare support and feedback handling", "Create support categories, draft response templates, escalation rules, refund/complaint triage and feedback capture. Do not send messages or promise refunds."),
            ("finance", "Validate costs, pricing and financial controls", "Record only evidenced costs and verified revenue inputs, estimate unit economics with assumptions visible, identify free-tier limits and flag any spend. No purchases, payments or financial commitments."),
            ("people-workforce", "Review departmental performance and workload", "Review outputs, missing evidence, workload and capability gaps. Propose role, workflow or training improvements for owner review; do not change permissions autonomously.")
        ]
    },
    "parallel-company-operating-cycle": {
        "name": "Parallel company-wide operating cycle",
        "description": "Parallel execution with explicit prerequisite gates and strict business isolation.",
        "steps": [
            ("executive", "Set objective, scope and owner decision gates", "Define the objective, selected business environment, measurable outcome, exclusions, risks and owner approval gates. Keep all business environments separate."),
            ("research", "Validate the opportunity with evidence", "Collect dated, attributable evidence about customers, demand, competitors and risks. Separate facts, estimates and hypotheses."),
            ("product", "Specify the offer and acceptance criteria", "Define the proposed offer, target buyer, deliverables, exclusions, acceptance criteria and assumptions."),
            ("design", "Prepare creative and production specifications", "Produce a detailed creative brief, visual direction, required assets, file formats and quality criteria."),
            ("engineering", "Assess technical delivery and integrations", "Define implementation tasks, dependencies, architecture, security and integration requirements. Prefer free/read-only options."),
            ("legal-compliance", "Review licensing, platform and policy risks", "Identify platform terms, intellectual-property, privacy and advertising-claim risks. Flag qualified legal review."),
            ("quality-assurance", "Verify deliverables and release readiness", "Create and execute safe tests; record evidence, defects and release blockers. Never mark untested work as passed."),
            ("marketing", "Prepare audience and campaign materials", "Develop positioning, channel strategy, content calendar and draft creative copy. Draft only."),
            ("sales-marketplace", "Prepare inbound sales and listing operations", "Prepare listing drafts, pricing hypotheses and enquiry qualification. Do not publish or accept orders."),
            ("customer-support", "Prepare support and feedback handling", "Create support categories, draft response templates and escalation rules. Do not send messages."),
            ("finance", "Validate costs, pricing and financial controls", "Record evidenced costs, estimate unit economics with assumptions visible and flag spend. No purchases or payments."),
            ("people-workforce", "Review departmental performance and workload", "Review outputs, workload and capability gaps. Propose improvements for owner review.")
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
            status TEXT NOT NULL DEFAULT 'blocked', output TEXT NOT NULL DEFAULT '', dependencies_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
            UNIQUE(workflow_id, sequence_no), UNIQUE(task_id),
            FOREIGN KEY(workflow_id) REFERENCES workflow_instances(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow ON workflow_steps(workflow_id, sequence_no);
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(workflow_instances)")}
        if "business_id" not in columns:
            db.execute("ALTER TABLE workflow_instances ADD COLUMN business_id TEXT NOT NULL DEFAULT 'core'")
        db.execute("CREATE INDEX IF NOT EXISTS idx_workflow_instances_scope ON workflow_instances(business_id, created_at)")
        step_columns = {row["name"] for row in db.execute("PRAGMA table_info(workflow_steps)")}
        if "output" not in step_columns:
            db.execute("ALTER TABLE workflow_steps ADD COLUMN output TEXT NOT NULL DEFAULT ''")
        if "dependencies_json" not in step_columns:
            db.execute("ALTER TABLE workflow_steps ADD COLUMN dependencies_json TEXT NOT NULL DEFAULT '[]'")

def list_templates() -> dict:
    return {"templates": [{"id": key, "name": value["name"], "description": value["description"],
        "step_count": len(value["steps"]), "departments": [s[0] for s in value["steps"]],
        "execution_mode": "parallel_dag" if key == "parallel-company-operating-cycle" else "sequential"}
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
            dependencies = list(COMPANY_CYCLE_DEPENDENCIES.get(index, ())) if template_id == "parallel-company-operating-cycle" else ([index - 1] if index > 1 else [])
            status = "queued" if not dependencies else "blocked"
            db.execute("""INSERT INTO tasks(id,title,description,department,business_id,status,created_at)
                VALUES(?,?,?,?,?,?,?)""", (task_id, title, description, department, business_id, status, now))
            step_id = str(uuid4())
            db.execute("""INSERT INTO workflow_steps
                (id,workflow_id,task_id,sequence_no,department,title,status,dependencies_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (step_id, workflow_id, task_id, index, department, title, status, json.dumps(dependencies), now))
            created.append({"id": step_id, "task_id": task_id, "sequence": index,
                            "department": department, "title": title, "status": status, "dependencies": dependencies})
    # Starting a workflow is an owner-authorized request for internal work. Queue only
    # its first step; later steps are queued automatically after successful handoff.
    from ai_os.agent_runtime import create_run
    for item in created:
        if item["status"] == "queued":
            create_run(item["task_id"])
    return {"id": workflow_id, "business_id": business_id, "template_id": template_id, "name": template["name"],
            "status": "active", "steps": created,
            "next_action": "All dependency-free departments are queued; dependent departments start when every prerequisite completes."}

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

def finish_workflow_task(task_id: str, success: bool, output: str = '') -> None:
    """Complete one node and release all nodes whose prerequisites are satisfied."""
    initialize_workflows()
    newly_queued = []
    with connect() as db:
        step = db.execute("SELECT * FROM workflow_steps WHERE task_id=?", (task_id,)).fetchone()
        if not step or step["status"] == "completed":
            return
        if not success:
            db.execute("UPDATE workflow_steps SET status='failed' WHERE task_id=?", (task_id,))
            db.execute("UPDATE workflow_instances SET status='blocked' WHERE id=?", (step["workflow_id"],))
            return
        db.execute("UPDATE workflow_steps SET status='completed', output=? WHERE task_id=?", (output[:12000], task_id))
        rows = db.execute("SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY sequence_no", (step["workflow_id"],)).fetchall()
        completed = {row["sequence_no"] for row in rows if row["status"] == "completed"}
        for candidate in rows:
            if candidate["status"] != "blocked":
                continue
            try:
                prerequisites = json.loads(candidate["dependencies_json"] or "[]")
            except (TypeError, ValueError):
                prerequisites = [candidate["sequence_no"] - 1] if candidate["sequence_no"] > 1 else []
            if not set(prerequisites).issubset(completed):
                continue
            upstream = [row for row in rows if row["sequence_no"] in prerequisites]
            handoff = "\n\nUPSTREAM DEPARTMENT HANDOFFS (verify claims):\n" + "\n".join(
                "[" + item["department"] + "] " + (item["output"] or "(No text output recorded.)")[:6000]
                for item in upstream
            )
            db.execute("UPDATE workflow_steps SET status='queued' WHERE id=?", (candidate["id"],))
            db.execute("UPDATE tasks SET status='queued', description=description || ? WHERE id=?", (handoff, candidate["task_id"]))
            newly_queued.append(dict(candidate))
        remaining = db.execute("SELECT COUNT(*) AS n FROM workflow_steps WHERE workflow_id=? AND status!='completed'", (step["workflow_id"],)).fetchone()["n"]
        if remaining == 0:
            db.execute("UPDATE workflow_instances SET status='completed' WHERE id=?", (step["workflow_id"],))
    if success and newly_queued:
        from ai_os.department_collaboration import send_message
        with connect() as db:
            current = db.execute("SELECT w.business_id,s.department FROM workflow_steps s JOIN workflow_instances w ON w.id=s.workflow_id WHERE s.task_id=?", (task_id,)).fetchone()
        for candidate in newly_queued:
            send_message(current["business_id"], current["department"], candidate["department"],
                         "Workflow dependency handoff", ("Completed upstream output:\n\n" + output)[:12000],
                         candidate["task_id"])
            from ai_os.agent_runtime import create_run
            create_run(candidate["task_id"])

def list_workflows(limit: int = 50, business_id: str = "core") -> list[dict]:
    if business_id not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    initialize_workflows()
    with connect() as db:
        rows = db.execute("SELECT id FROM workflow_instances WHERE business_id=? ORDER BY created_at DESC LIMIT ?", (business_id, max(1, min(limit, 100)))).fetchall()
    return [item for row in rows if (item := get_workflow(row["id"])) is not None]
