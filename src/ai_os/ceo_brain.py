"""CEO objective decomposition using transparent deterministic routing rules.

No LLM, external API, or tool is invoked here. The CEO remains accountable;
this module creates a reviewable project plan and persists it for execution.
"""
import json
from datetime import datetime, timezone

from ai_os.db import connect
from ai_os.execution import create_company_run, get_company_run
from ai_os.execution_schemas import CompanyRunCreate, RunStepCreate
from ai_os.registry import get_agent, select_agent
from ai_os.ceo_schemas import CEOObjectiveCreate

CEO_AGENT_ID = "company-orchestrator"
PLANNING_MODE = "deterministic_rules_v1"

BASE_ROLES = [
    ("discover", "research-synthesist", "Research the objective, relevant market/problem, available evidence, and unknowns. Separate sourced facts from assumptions."),
    ("validate_market", "product-trend-researcher", "Investigate customer demand, alternatives, competitors, buying signals, and evidence of willingness to pay relevant to the objective."),
    ("define_offer", "product-manager", "Turn the objective and research into a focused offer or solution scope, target customer, acceptance criteria, and smallest testable milestone."),
    ("coordinate", "project-manager-senior", "Create a practical milestone sequence, dependencies, owner roles, risks, and progress checkpoints. Do not assume paid tools or external access."),
    ("growth_plan", "marketing-growth-hacker", "Prepare an organic, permission-respecting customer acquisition plan. Prefer discoverability and useful content; do not use cold outreach or paid promotion."),
    ("content_drafts", "marketing-content-creator", "Prepare channel-adapted content drafts and a publishing calendar for CEO review. Do not publish or contact anyone."),
    ("support_readiness", "support-support-responder", "Prepare a customer support FAQ, issue categories, escalation rules, and draft response patterns. Do not contact customers or make commitments."),
    ("measure_learn", "support-analytics-reporter", "Define a simple measurement plan, baseline metrics, evidence collection, weekly review, and learning loop for the objective."),
    ("quality_gate", "testing-reality-checker", "Review the proposed offer and plan for unsupported claims, missing evidence, feasibility gaps, risks, and clear pass/fail criteria."),
]

OPTIONAL_ROLES = {
    "engineering": {
        "terms": ("website", "wordpress", "woocommerce", "store", "checkout", "automation", "integration", "api", "software", "app", "platform", "code", "backend", "frontend", "deploy"),
        "role": ("build_solution", "engineering-backend-architect", "Design the minimum technical approach needed for the objective. Identify free-first options, dependencies, security risks, and what must remain unimplemented pending approval."),
        "reason": "Technical implementation keywords were found in the objective or context.",
    },
    "design": {
        "terms": ("design", "brand", "logo", "visual", "3d", "asset", "character", "ui", "ux", "graphic", "illustration"),
        "role": ("design_direction", "design-ui-designer", "Define the visual direction and practical design requirements relevant to the objective. Produce reviewable specifications only; do not publish assets."),
        "reason": "Visual/design keywords were found in the objective or context.",
    },
    "finance": {
        "terms": ("pricing", "price", "revenue", "profit", "budget", "cost", "financial", "monetization", "monetize", "cashflow"),
        "role": ("unit_economics", "finance-financial-analyst", "Estimate costs, pricing considerations, break-even assumptions, and financial risks using evidence. Do not initiate payments or financial changes."),
        "reason": "Financial planning keywords were found in the objective or context.",
    },
    "security": {
        "terms": ("security", "privacy", "credential", "authentication", "access control", "token", "compliance", "data protection"),
        "role": ("security_review", "security-architect", "Review data handling, permissions, secrets, threat exposure, and minimum security controls. Do not change production permissions or credentials."),
        "reason": "Security/privacy keywords were found in the objective or context.",
    },
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _matches(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)

def _resolve_agent(preferred_id: str, department: str):
    agent = get_agent(preferred_id)
    if agent and agent.enabled:
        return agent
    fallback = select_agent(department)
    if fallback and fallback.enabled:
        return fallback
    raise LookupError(f"No enabled specialist is available for required department '{department}'")

def create_ceo_plan(payload: CEOObjectiveCreate) -> dict:
    objective = payload.objective.strip()
    if not objective:
        raise ValueError("Objective must not be blank")
    scan_text = f"{objective}\n{payload.context}".lower()

    selected = list(BASE_ROLES)
    reasons = {
        "discover": "Baseline discovery is required for every company objective.",
        "validate_market": "Every business objective needs evidence of customer demand and alternatives.",
        "define_offer": "Every objective needs a scoped offer or solution and acceptance criteria.",
        "coordinate": "The CEO needs milestones, dependencies, and accountable work tracking.",
        "growth_plan": "The company needs a free-first, organic route to customer discovery.",
        "content_drafts": "Content drafts support discoverability; publication remains gated.",
        "support_readiness": "Customer issues need prepared, non-committal response guidance.",
        "measure_learn": "The company needs measurable outcomes and a feedback loop.",
        "quality_gate": "A separate quality review checks evidence, feasibility, and risk.",
    }

    optional = []
    for department, config in OPTIONAL_ROLES.items():
        if _matches(scan_text, config["terms"]):
            optional.append((department, config["role"]))
            reasons[config["role"][0]] = config["reason"]

    role_map = {}
    decision_log = []
    for key, preferred_id, task in selected + [role for _, role in optional]:
        department = preferred_id.split("-", 1)[0]
        agent = _resolve_agent(preferred_id, department)
        role_map[key] = agent
        decision_log.append({
            "step_key": key,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "department": agent.department,
            "reason": reasons.get(key, "Selected by the CEO planning rules for this objective."),
        })

    steps = []
    # Sequential core gates make the evidence and offer prerequisites explicit.
    dependencies = {
        "discover": [],
        "validate_market": ["discover"],
        "define_offer": ["validate_market"],
        "coordinate": ["define_offer"],
        "growth_plan": ["define_offer", "coordinate"],
        "content_drafts": ["growth_plan"],
        "support_readiness": ["define_offer"],
        "measure_learn": ["content_drafts", "support_readiness"],
        "quality_gate": ["measure_learn"],
    }
    for department, (key, preferred_id, task) in optional:
        dependencies[key] = ["define_offer"]

    for key, preferred_id, task in selected + [role for _, role in optional]:
        agent = role_map[key]
        full_task = (
            f"Company objective: {objective}\n\n"
            f"Assigned CEO workstream: {task}\n\n"
            "Constraints and operating rules: " + (payload.constraints.strip() or "Use free-first options; no external actions without CEO and owner approval.") +
            "\n\nReturn evidence, assumptions, blockers, and recommendations to the CEO Agent."
        )
        context = (
            f"Objective context: {payload.context.strip() or '(No additional context supplied.)'}\n"
            f"Planning method: {PLANNING_MODE}. This plan was generated using deterministic routing rules, not model reasoning."
        )
        steps.append(RunStepCreate(
            step_key=key,
            agent_id=agent.id,
            task=full_task,
            context=context,
            depends_on=dependencies[key],
        ))

    selected_departments = list(dict.fromkeys(item["department"] for item in decision_log))
    run_payload = CompanyRunCreate(
        title=f"CEO plan: {objective[:160]}",
        description=f"CEO-generated plan ({PLANNING_MODE}). Objective: {objective}",
        steps=steps,
    )
    run = create_company_run(run_payload)
    metadata = {
        "run_id": run["id"],
        "objective": objective,
        "planning_mode": PLANNING_MODE,
        "selected_workstreams": selected_departments,
        "decision_log": decision_log,
        "created_at": _now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO ceo_plan_metadata
               (run_id, objective, planning_mode, selected_workstreams_json, decision_log_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run["id"], objective, PLANNING_MODE, json.dumps(selected_departments),
             json.dumps(decision_log), metadata["created_at"]),
        )
    return {
        **metadata,
        "accountable_agent_id": CEO_AGENT_ID,
        "run": run,
        "limitations": [
            "Planning uses deterministic keyword rules; no AI model was invoked.",
            "Specialist steps are queued only. No model calls, external tools, publishing, spending, or customer contact occurred.",
            "The CEO remains accountable; owner approval is still required for sensitive external actions.",
        ],
    }

def get_ceo_plan(run_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM ceo_plan_metadata WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return None
    run = get_company_run(run_id)
    if run is None:
        return None
    return {
        "run_id": row["run_id"],
        "objective": row["objective"],
        "planning_mode": row["planning_mode"],
        "selected_workstreams": json.loads(row["selected_workstreams_json"]),
        "decision_log": json.loads(row["decision_log_json"]),
        "created_at": row["created_at"],
        "accountable_agent_id": CEO_AGENT_ID,
        "run": run,
        "limitations": [
            "Planning uses deterministic keyword rules; no AI model was invoked.",
            "Specialist steps are queued only. No model calls or external actions were performed.",
        ],
    }
