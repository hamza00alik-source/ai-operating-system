"""Persistent CEO-coordinated company runs with dependency-aware specialist handoffs.

This is a durable workflow layer, not autonomous AI execution. It creates work
packets locally; a human/CEO-controlled runtime must deliver them to a model.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.work_packets import build_work_packet
from ai_os.execution_schemas import CompanyRunCreate, StepReportCreate

CEO_AGENT_ID = "company-orchestrator"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _decode_step(row) -> dict:
    item = dict(row)
    item["depends_on"] = json.loads(item.pop("depends_on_json"))
    item["work_packet"] = json.loads(item["work_packet_json"]) if item["work_packet_json"] else None
    item["report"] = json.loads(item["report_json"]) if item["report_json"] else None
    return item

def _run_dict(db, run_row) -> dict:
    run = dict(run_row)
    rows = db.execute(
        "SELECT * FROM company_run_steps WHERE run_id=? ORDER BY position ASC",
        (run["id"],),
    ).fetchall()
    run["steps"] = [_decode_step(row) for row in rows]
    run["accountable_agent_id"] = CEO_AGENT_ID
    return run

def _validate_graph(payload: CompanyRunCreate) -> None:
    keys = [step.step_key for step in payload.steps]
    if len(keys) != len(set(keys)):
        raise ValueError("step_key values must be unique")
    known = set(keys)
    for step in payload.steps:
        if len(step.depends_on) != len(set(step.depends_on)):
            raise ValueError(f"Step {step.step_key} contains duplicate dependencies")
        missing = set(step.depends_on) - known
        if missing:
            raise ValueError(f"Step {step.step_key} references unknown dependencies: {', '.join(sorted(missing))}")
        if step.step_key in step.depends_on:
            raise ValueError(f"Step {step.step_key} cannot depend on itself")
        from ai_os.control_plane import get_effective_agent
        agent = get_effective_agent(step.agent_id)
        if agent is None or step.agent_id == CEO_AGENT_ID:
            raise ValueError(f"Step {step.step_key} must name an enabled specialist agent")

    graph = {step.step_key: step.depends_on for step in payload.steps}
    visiting, visited = set(), set()
    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("Company run dependencies must be acyclic")
        if key in visited:
            return
        visiting.add(key)
        for parent in graph[key]:
            visit(parent)
        visiting.remove(key)
        visited.add(key)
    for key in graph:
        visit(key)

def create_company_run(payload: CompanyRunCreate) -> dict:
    _validate_graph(payload)
    now, run_id = _now(), str(uuid4())
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """INSERT INTO company_runs(id,title,description,status,created_at,updated_at)
               VALUES(?,?,?,'queued',?,?)""",
            (run_id, payload.title.strip(), payload.description.strip(), now, now),
        )
        for position, step in enumerate(payload.steps):
            db.execute(
                """INSERT INTO company_run_steps
                (run_id,step_key,agent_id,task,context,depends_on_json,status,position,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'pending',?,?,?)""",
                (run_id, step.step_key, step.agent_id, step.task.strip(), step.context.strip(),
                 json.dumps(step.depends_on), position, now, now),
            )
        row = db.execute("SELECT * FROM company_runs WHERE id=?", (run_id,)).fetchone()
        return _run_dict(db, row)

def list_company_runs(limit: int = 100) -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM company_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_run_dict(db, row) for row in rows]

def get_company_run(run_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM company_runs WHERE id=?", (run_id,)).fetchone()
        return _run_dict(db, row) if row else None

def dispatch_ready_step(run_id: str, step_key: str) -> dict:
    """Create and persist a packet only when every dependency is completed."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        run = db.execute("SELECT * FROM company_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise LookupError("Company run not found")
        step = db.execute(
            "SELECT * FROM company_run_steps WHERE run_id=? AND step_key=?",
            (run_id, step_key),
        ).fetchone()
        if step is None:
            raise LookupError("Company run step not found")
        if step["status"] == "assigned" and step["work_packet_json"]:
            return _decode_step(step)
        if step["status"] != "pending":
            raise ValueError(f"Step cannot be dispatched from status {step['status']}")
        dependencies = json.loads(step["depends_on_json"])
        if dependencies:
            placeholders = ",".join("?" for _ in dependencies)
            rows = db.execute(
                f"SELECT step_key,status FROM company_run_steps WHERE run_id=? AND step_key IN ({placeholders})",
                (run_id, *dependencies),
            ).fetchall()
            completed = {row["step_key"] for row in rows if row["status"] == "completed"}
            if completed != set(dependencies):
                raise ValueError("Step is not ready: all dependencies must be completed first")
        packet = build_work_packet(step["agent_id"], step["task"], step["context"])
        now = _now()
        db.execute(
            """UPDATE company_run_steps SET status='assigned',work_packet_json=?,updated_at=?
               WHERE run_id=? AND step_key=? AND status='pending'""",
            (json.dumps(packet, separators=(",", ":")), now, run_id, step_key),
        )
        db.execute(
            "UPDATE company_runs SET status='running',updated_at=? WHERE id=? AND status='queued'",
            (now, run_id),
        )
        updated = db.execute(
            "SELECT * FROM company_run_steps WHERE run_id=? AND step_key=?",
            (run_id, step_key),
        ).fetchone()
        return _decode_step(updated)


def propagate_blocked_steps(run_id: str) -> int:
    """Block pending descendants of failed steps and finalize the run state."""
    blocked_count = 0
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        run = db.execute("SELECT * FROM company_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise LookupError("Company run not found")
        while True:
            rows = db.execute(
                "SELECT step_key,depends_on_json,status FROM company_run_steps WHERE run_id=?",
                (run_id,),
            ).fetchall()
            states = {row["step_key"]: row["status"] for row in rows}
            newly_blocked = []
            for row in rows:
                if row["status"] != "pending":
                    continue
                failed_dependencies = [
                    key for key in json.loads(row["depends_on_json"])
                    if states.get(key) == "blocked"
                ]
                if failed_dependencies:
                    newly_blocked.append((row["step_key"], failed_dependencies))
            if not newly_blocked:
                break
            now = _now()
            for step_key, failed_dependencies in newly_blocked:
                report = {
                    "status": "blocked",
                    "summary": "This step was not run because a required dependency was blocked.",
                    "evidence": [],
                    "blockers": [
                        "Blocked dependency: " + ", ".join(failed_dependencies)
                    ],
                    "reported_to": CEO_AGENT_ID,
                    "system_generated": True,
                }
                changed = db.execute(
                    """UPDATE company_run_steps SET status='blocked',report_json=?,updated_at=?
                       WHERE run_id=? AND step_key=? AND status='pending'""",
                    (json.dumps(report, separators=(",", ":")), now, run_id, step_key),
                ).rowcount
                blocked_count += changed
        counts = db.execute(
            """SELECT
                 SUM(CASE WHEN status NOT IN ('completed','blocked') THEN 1 ELSE 0 END) AS remaining,
                 SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) AS blocked,
                 SUM(CASE WHEN status IN ('assigned','completed','blocked') THEN 1 ELSE 0 END) AS started
               FROM company_run_steps WHERE run_id=?""",
            (run_id,),
        ).fetchone()
        if counts["remaining"] == 0:
            run_status = "blocked" if counts["blocked"] else "completed"
        else:
            run_status = "running" if counts["started"] else "queued"
        db.execute(
            "UPDATE company_runs SET status=?,updated_at=? WHERE id=?",
            (run_status, _now(), run_id),
        )
    return blocked_count


def mark_company_step_blocked(run_id: str, step_key: str, reason: str) -> bool:
    """Mark an assigned step blocked after its durable job exhausts retries."""
    report = {
        "status": "blocked",
        "summary": "The specialist job exhausted its retry allowance and was stopped.",
        "evidence": [],
        "blockers": [reason.strip()[:1000] or "Worker retry limit reached."],
        "reported_to": CEO_AGENT_ID,
        "system_generated": True,
    }
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = _now()
        changed = db.execute(
            """UPDATE company_run_steps SET status='blocked',report_json=?,updated_at=?
               WHERE run_id=? AND step_key=? AND status='assigned'""",
            (json.dumps(report, separators=(",", ":")), now, run_id, step_key),
        ).rowcount
        if changed:
            db.execute(
                "UPDATE company_runs SET status='running',updated_at=? WHERE id=?",
                (now, run_id),
            )
    if changed:
        propagate_blocked_steps(run_id)
    return bool(changed)

def submit_step_report(run_id: str, step_key: str, payload: StepReportCreate) -> dict:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        step = db.execute(
            "SELECT * FROM company_run_steps WHERE run_id=? AND step_key=?",
            (run_id, step_key),
        ).fetchone()
        if step is None:
            raise LookupError("Company run step not found")
        if step["status"] != "assigned":
            raise ValueError("A report can be submitted only for an assigned step")
        report = {
            "status": payload.status,
            "summary": payload.summary.strip(),
            "evidence": payload.evidence,
            "blockers": payload.blockers,
            "reported_to": CEO_AGENT_ID,
        }
        now = _now()
        db.execute(
            """UPDATE company_run_steps SET status=?,report_json=?,updated_at=?
               WHERE run_id=? AND step_key=? AND status='assigned'""",
            (payload.status, json.dumps(report, separators=(",", ":")), now, run_id, step_key),
        )
        remaining = db.execute(
            "SELECT COUNT(*) AS n FROM company_run_steps WHERE run_id=? AND status NOT IN ('completed','blocked')",
            (run_id,),
        ).fetchone()["n"]
        blocked = db.execute(
            "SELECT COUNT(*) AS n FROM company_run_steps WHERE run_id=? AND status='blocked'",
            (run_id,),
        ).fetchone()["n"]
        run_status = "completed" if remaining == 0 and blocked == 0 else ("blocked" if remaining == 0 else "running")
        db.execute("UPDATE company_runs SET status=?,updated_at=? WHERE id=?", (run_status, now, run_id))
        updated = db.execute(
            "SELECT * FROM company_run_steps WHERE run_id=? AND step_key=?",
            (run_id, step_key),
        ).fetchone()
        return _decode_step(updated)
