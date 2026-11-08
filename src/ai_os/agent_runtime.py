"""Persistent, owner-triggered research analyst agent.

This first agent is deliberately analysis-only: it can use the configured LLM
gateway and save its result, but it cannot browse, execute code, spend money,
publish, contact customers, or call external tools.
"""
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.llm_gateway import generate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_research_analyst(provider: str, goal: str) -> dict:
    run_id = str(uuid4())
    created_at = _now()
    with connect() as db:
        db.execute(
            """INSERT INTO agent_runs
               (id,agent_type,goal,provider,status,created_at)
               VALUES (?,?,?,?,?,?)""",
            (run_id, "research_analyst", goal, provider, "running", created_at),
        )

    prompt = (
        "You are the Research Analyst agent inside a human-supervised AI company.\n"
        "Perform careful analysis of the user's supplied brief. Separate facts "
        "provided by the user from assumptions and unknowns. Do not invent "
        "sources, current market data, prices, or claims of external research. "
        "If external evidence is needed but unavailable, say so clearly.\n"
        "Return: Executive summary; key findings; assumptions and unknowns; "
        "recommended next actions; risks.\n"
        "You are analysis-only. Do not claim to have taken external actions. "
        "Do not spend money, publish, contact anyone, or make commitments.\n\n"
        "USER BRIEF:\n" + goal
    )
    try:
        result = generate(provider, prompt)
        finished_at = _now()
        with connect() as db:
            db.execute(
                """UPDATE agent_runs
                   SET status='completed',output=?,model=?,latency_ms=?,finished_at=?
                   WHERE id=? AND status='running'""",
                (result["response"], result.get("model"), result.get("latency_ms"),
                 finished_at, run_id),
            )
    except Exception as exc:
        finished_at = _now()
        with connect() as db:
            db.execute(
                """UPDATE agent_runs SET status='failed',error=?,finished_at=?
                   WHERE id=? AND status='running'""",
                (str(exc)[:500], finished_at, run_id),
            )
        raise

    return get_agent_run(run_id)


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
