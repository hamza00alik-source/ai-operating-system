"""Durable queue and runtime for the first owner-triggered AI agent.

Research Analyst is analysis-only. It can call the guarded LLM gateway and save
its result, but cannot browse, execute code, spend money, publish, or contact users.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.llm_gateway import generate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_research_analyst(provider: str, goal: str) -> dict:
    run = {
        "id": str(uuid4()),
        "agent_type": "research_analyst",
        "goal": goal,
        "provider": provider,
        "status": "queued",
        "output": "",
        "error": None,
        "created_at": _now(),
        "finished_at": None,
    }
    with connect() as db:
        db.execute(
            """INSERT INTO agent_runs
               (id,agent_type,goal,provider,status,output,error,created_at,finished_at)
               VALUES (:id,:agent_type,:goal,:provider,:status,:output,:error,:created_at,:finished_at)""",
            run,
        )
    return run


def claim_agent_run(worker_id: str | None = None) -> dict | None:
    """Atomically claim one queued or abandoned run; safe across worker processes."""
    worker_id = worker_id or f"agent-worker-{uuid4()}"
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()
    lease_until = (now + timedelta(minutes=5)).isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """UPDATE agent_runs SET status='failed',
               error='Worker lease expired after retry limit',
               finished_at=?,lease_owner=NULL,lease_expires_at=NULL
               WHERE status='running' AND attempts>=3
               AND (lease_expires_at IS NULL OR lease_expires_at < ?)""",
            (timestamp, timestamp),
        )
        row = db.execute(
            """SELECT * FROM agent_runs WHERE attempts < 3 AND (
                 status='queued' OR (status='running' AND
                 (lease_expires_at IS NULL OR lease_expires_at < ?))
               ) ORDER BY created_at LIMIT 1""",
            (timestamp,),
        ).fetchone()
        if row is None:
            return None
        changed = db.execute(
            """UPDATE agent_runs SET status='running',lease_owner=?,
               lease_expires_at=?,attempts=COALESCE(attempts,0)+1,error=NULL
               WHERE id=? AND attempts < 3 AND (
                 status='queued' OR (status='running' AND
                 (lease_expires_at IS NULL OR lease_expires_at < ?))
               )""",
            (worker_id, lease_until, row["id"], timestamp),
        ).rowcount
        if changed != 1:
            return None
        claimed = db.execute("SELECT * FROM agent_runs WHERE id=?", (row["id"],)).fetchone()
        return dict(claimed)


def _build_prompt(goal: str) -> str:
    return (
        "You are the Research Analyst agent inside a human-supervised AI company.\n"
        "Analyze the user's supplied brief. Separate facts provided by the user "
        "from assumptions and unknowns. Do not invent sources, current market "
        "data, prices, or claims of external research. If external evidence is "
        "needed but unavailable, say so clearly.\n"
        "Return: Executive summary; key findings; assumptions and unknowns; "
        "recommended next actions; risks.\n"
        "You are analysis-only. Do not claim to have taken external actions. "
        "Do not spend money, publish, contact anyone, or make commitments.\n\n"
        "USER BRIEF:\n" + goal
    )


def process_claimed_agent_run(run: dict) -> dict:
    run_id, worker_id = run["id"], run["lease_owner"]
    try:
        result = generate(run["provider"], _build_prompt(run["goal"]))
        with connect() as db:
            db.execute(
                """UPDATE agent_runs SET status='completed',output=?,model=?,
                   latency_ms=?,finished_at=?,lease_owner=NULL,lease_expires_at=NULL
                   WHERE id=? AND status='running' AND lease_owner=?""",
                (result["response"], result.get("model"), result.get("latency_ms"),
                 _now(), run_id, worker_id),
            )
    except Exception as exc:
        with connect() as db:
            db.execute(
                """UPDATE agent_runs SET status='failed',error=?,finished_at=?,
                   lease_owner=NULL,lease_expires_at=NULL
                   WHERE id=? AND status='running' AND lease_owner=?""",
                (str(exc)[:500], _now(), run_id, worker_id),
            )
    return get_agent_run(run_id)


def run_pending_once(worker_id: str | None = None) -> bool:
    claimed = claim_agent_run(worker_id=worker_id)
    if claimed is None:
        return False
    process_claimed_agent_run(claimed)
    return True


def get_agent_run(run_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_agent_runs(limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]
