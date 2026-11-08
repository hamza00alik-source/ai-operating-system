"""Durable sequential agent workflow with SQLite-backed handoffs."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from ai_os.db import connect
from ai_os.model_adapter import generate_text


AGENT_STEPS = (
    (
        "researcher",
        "Researcher",
        "Analyze the task, identify requirements, assumptions, risks and a practical plan. "
        "Separate known facts from assumptions. Do not invent research or claim to have browsed.",
    ),
    (
        "developer",
        "Developer",
        "Create the requested draft, implementation proposal or work product. "
        "Use the Researcher's handoff from shared memory. Do not deploy, publish, spend, "
        "contact customers or change external systems.",
    ),
    (
        "quality_reviewer",
        "Quality Reviewer",
        "Independently review the Developer's work against the original task and Researcher's "
        "handoff. Identify errors, missing requirements and safety issues, then return the "
        "corrected final deliverable. Do not claim tests or actions that were not performed.",
    ),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def schedule_ready_steps() -> dict:
    """The sequential workflow is driven by run_agent_workflow, not a separate scheduler."""
    return {"scheduled": 0}


def get_task_memory(task_id: str) -> list[dict]:
    """Return durable, task-scoped inter-agent handoffs in insertion order."""
    with connect() as db:
        rows = db.execute(
            "SELECT memory_key, source_agent, content, created_at "
            "FROM agent_memory WHERE task_id=? ORDER BY id ASC",
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_task_steps(task_id: str) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT step_key, agent_name, status, error, worker_id, "
            "started_at, finished_at FROM agent_steps WHERE task_id=? ORDER BY id ASC",
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def run_agent_workflow(task: dict, *, worker_id: str) -> str:
    """Run Researcher -> Developer -> Quality Reviewer with durable handoffs.

    Completed steps are reused if an operator deliberately resumes a task.
    A pre-existing running/failed step is never automatically retried because
    the provider may already have received its request before a crash/timeout.
    """
    task_id = task["id"]
    final_output = None

    for step_key, agent_name, instructions in AGENT_STEPS:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT status, output FROM agent_steps WHERE task_id=? AND step_key=?",
                (task_id, step_key),
            ).fetchone()
            if existing and existing["status"] == "completed":
                output = existing["output"]
                if not output:
                    raise RuntimeError(f"Completed {agent_name} step has no persisted output")
                final_output = output
                continue
            if existing:
                raise RuntimeError(
                    f"{agent_name} step is {existing['status']}; manual review is required "
                    "before any provider request can be repeated"
                )

            memory_rows = db.execute(
                "SELECT source_agent, content FROM agent_memory "
                "WHERE task_id=? ORDER BY id ASC",
                (task_id,),
            ).fetchall()
            memory_text = "\n\n".join(
                f"--- Handoff from {row['source_agent']} ---\n{row['content']}"
                for row in memory_rows
            ) or "(No earlier agent handoffs.)"
            prompt = (
                f"You are the {agent_name} agent in a human-supervised AI company workflow.\n"
                f"Your role: {instructions}\n\n"
                f"Original task title: {task['title']}\n"
                f"Original task details: {task['description']}\n"
                f"Department: {task['department']}\n\n"
                f"Shared persistent memory and prior handoffs:\n{memory_text}\n\n"
                "Safety boundary: produce internal work only. Do not publish, spend money, "
                "contact customers, make commitments, or modify external systems. "
                "Be explicit about uncertainty and unverified claims."
            )
            started_at = _now()
            db.execute(
                """INSERT INTO agent_steps
                   (task_id,step_key,agent_name,status,prompt,worker_id,started_at)
                   VALUES (?,?,?,'running',?,?,?)""",
                (task_id, step_key, agent_name, prompt, worker_id, started_at),
            )

        try:
            output = generate_text(prompt)
            if not isinstance(output, str) or not output.strip():
                raise RuntimeError(f"{agent_name} returned empty output")
            output = output.strip()
        except Exception as exc:
            with connect() as db:
                db.execute(
                    "UPDATE agent_steps SET status='failed', error=?, finished_at=? "
                    "WHERE task_id=? AND step_key=? AND status='running'",
                    (f"{type(exc).__name__}: {str(exc)[:1000]}", _now(), task_id, step_key),
                )
            raise

        finished_at = _now()
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE agent_steps SET status='completed', output=?, finished_at=? "
                "WHERE task_id=? AND step_key=? AND status='running' AND worker_id=?",
                (output, finished_at, task_id, step_key, worker_id),
            ).rowcount
            if changed != 1:
                raise RuntimeError(
                    f"{agent_name} handoff could not be persisted; manual review required"
                )
            db.execute(
                """INSERT INTO agent_memory
                   (task_id,memory_key,source_agent,content,created_at)
                   VALUES (?,?,?,?,?)""",
                (task_id, f"{step_key}.output", agent_name, output, finished_at),
            )
        final_output = output

    if final_output is None:
        raise RuntimeError("Agent workflow produced no final output")
    return final_output


def agent_graph_enabled() -> bool:
    """Require explicit opt-in because a graph uses three model requests per task."""
    return os.getenv("AI_OS_AGENT_GRAPH_ENABLED", "false").strip().lower() in {
        "1", "true", "yes",
    }
