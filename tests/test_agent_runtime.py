import sqlite3

import pytest

from ai_os.agent_runtime import get_task_memory, list_task_steps, run_agent_workflow
from ai_os.db import initialize_database


def _seed_task(monkeypatch, tmp_path):
    database = tmp_path / "agent-runtime.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    with sqlite3.connect(database) as db:
        db.execute(
            """INSERT INTO tasks
               (id,title,description,department,status,created_at)
               VALUES (?,?,?,?,?,?)""",
            ("task-agent-1", "Prepare launch plan", "Research and draft a launch plan",
             "marketing", "running", "2026-11-08T00:00:00+00:00"),
        )
    return database, {
        "id": "task-agent-1", "title": "Prepare launch plan",
        "description": "Research and draft a launch plan", "department": "marketing",
    }


def test_agents_share_persisted_handoffs_and_resume_completed_steps(monkeypatch, tmp_path):
    _database, task = _seed_task(monkeypatch, tmp_path)
    calls = []

    def fake_generate(prompt):
        calls.append(prompt)
        return f"output-{len(calls)}"

    monkeypatch.setattr("ai_os.agent_runtime.generate_text", fake_generate)
    first_result = run_agent_workflow(task, worker_id="agent-worker-a")

    assert first_result == "output-3"
    assert len(calls) == 3
    assert "output-1" in calls[1]
    assert "output-1" in calls[2]
    assert "output-2" in calls[2]

    memory = get_task_memory(task["id"])
    assert [item["source_agent"] for item in memory] == [
        "Researcher", "Developer", "Quality Reviewer"
    ]
    steps = list_task_steps(task["id"])
    assert [item["status"] for item in steps] == ["completed", "completed", "completed"]

    resumed_result = run_agent_workflow(task, worker_id="agent-worker-b")
    assert resumed_result == "output-3"
    assert len(calls) == 3


def test_failed_agent_step_is_not_automatically_retried(monkeypatch, tmp_path):
    _database, task = _seed_task(monkeypatch, tmp_path)
    calls = []

    def fail_on_second(prompt):
        calls.append(prompt)
        if len(calls) == 2:
            raise TimeoutError("provider timed out")
        return f"output-{len(calls)}"

    monkeypatch.setattr("ai_os.agent_runtime.generate_text", fail_on_second)
    with pytest.raises(TimeoutError, match="timed out"):
        run_agent_workflow(task, worker_id="agent-worker-a")

    assert len(get_task_memory(task["id"])) == 1
    steps = list_task_steps(task["id"])
    assert [item["status"] for item in steps] == ["completed", "failed"]

    with pytest.raises(RuntimeError, match="manual review"):
        run_agent_workflow(task, worker_id="agent-worker-b")
    assert len(calls) == 2
