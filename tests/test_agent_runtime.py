import json
import sqlite3

import pytest

from ai_os.agent_runtime import (
    AgentPausedForApproval, get_task_memory, list_task_steps, run_agent_workflow,
)
from ai_os.db import initialize_database


def _seed_task(monkeypatch, tmp_path, *, with_server=False):
    database = tmp_path / "agent-runtime.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    with sqlite3.connect(database) as db:
        db.execute(
            """INSERT INTO tasks (id,title,description,department,status,created_at)
               VALUES (?,?,?,?,?,?)""",
            ("task-agent-1", "Prepare launch plan", "Research and draft a launch plan",
             "marketing", "running", "2026-11-08T00:00:00+00:00"),
        )
        if with_server:
            db.execute(
                """INSERT INTO mcp_servers
                   (id,name,endpoint,transport,credential_env_json,capabilities_json,enabled,created_at,updated_at)
                   VALUES (?,?,?,'streamable_http','[]','[]',1,?,?)""",
                ("server-1", "Research MCP", "https://mcp.example.com/mcp",
                 "2026-11-08T00:00:00+00:00", "2026-11-08T00:00:00+00:00"),
            )
    return database, {
        "id": "task-agent-1", "title": "Prepare launch plan",
        "description": "Research and draft a launch plan", "department": "marketing",
    }


def test_agents_share_persisted_handoffs_and_resume_completed_steps(monkeypatch, tmp_path):
    _database, task = _seed_task(monkeypatch, tmp_path)
    calls = []

    def fake_turn(prompt, tools):
        calls.append(prompt)
        return {"kind": "final", "content": f"output-{len(calls)}"}

    monkeypatch.setattr("ai_os.agent_runtime.discover_enabled_tool_catalog", lambda: [])
    monkeypatch.setattr("ai_os.agent_runtime.generate_agent_turn", fake_turn)
    assert run_agent_workflow(task, worker_id="agent-worker-a") == "output-3"
    assert len(calls) == 3
    memory = get_task_memory(task["id"])
    assert [item["source_agent"] for item in memory] == [
        "Researcher", "Developer", "Quality Reviewer"
    ]
    assert [item["status"] for item in list_task_steps(task["id"])] == [
        "completed", "completed", "completed"
    ]
    assert run_agent_workflow(task, worker_id="agent-worker-b") == "output-3"
    assert len(calls) == 3


def test_failed_agent_step_is_not_automatically_retried(monkeypatch, tmp_path):
    _database, task = _seed_task(monkeypatch, tmp_path)
    calls = []

    def fail_on_second(prompt, tools):
        calls.append(prompt)
        if len(calls) == 2:
            raise TimeoutError("provider timed out")
        return {"kind": "final", "content": f"output-{len(calls)}"}

    monkeypatch.setattr("ai_os.agent_runtime.discover_enabled_tool_catalog", lambda: [])
    monkeypatch.setattr("ai_os.agent_runtime.generate_agent_turn", fail_on_second)
    with pytest.raises(TimeoutError, match="timed out"):
        run_agent_workflow(task, worker_id="agent-worker-a")
    assert len(get_task_memory(task["id"])) == 1
    assert [item["status"] for item in list_task_steps(task["id"])] == ["completed", "failed"]
    with pytest.raises(RuntimeError, match="manual review"):
        run_agent_workflow(task, worker_id="agent-worker-b")
    assert len(calls) == 2


def test_agent_tool_request_pauses_and_resumes_after_owner_result(monkeypatch, tmp_path):
    database, task = _seed_task(monkeypatch, tmp_path, with_server=True)
    catalog = [{
        "server_id": "server-1", "server_name": "Research MCP",
        "tool_name": "search", "description": "Search public data",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }]
    calls = []

    def fake_turn(prompt, tools):
        calls.append((prompt, tools))
        if len(calls) == 1:
            return {"kind": "tool_call", "tool_name": "aios_tool_0",
                    "arguments": {"query": "market size"}}
        return {"kind": "final", "content": "Research completed using approved search result."}

    monkeypatch.setattr("ai_os.agent_runtime.discover_enabled_tool_catalog", lambda: catalog)
    monkeypatch.setattr("ai_os.agent_runtime.generate_agent_turn", fake_turn)
    with pytest.raises(AgentPausedForApproval):
        run_agent_workflow(task, worker_id="worker-a")

    steps = list_task_steps(task["id"])
    assert steps[0]["status"] == "awaiting_approval"
    request_id = steps[0]["pending_mcp_request_id"]
    with sqlite3.connect(database) as db:
        request = db.execute(
            "SELECT requester_id,task_id,status FROM mcp_tool_requests WHERE id=?",
            (request_id,),
        ).fetchone()
        assert request == ("agent:researcher", task["id"], "pending")
        db.execute(
            "UPDATE mcp_tool_requests SET status='executed',result_json=?,updated_at=? WHERE id=?",
            (json.dumps({"result": "credible synthetic market data"}), "2026-11-08T01:00:00+00:00", request_id),
        )
    # A completed owner-approved result must remain resumable even if the MCP
    # server becomes unavailable before the worker restarts.
    def unavailable_catalog():
        raise ConnectionError("temporary MCP outage")

    monkeypatch.setattr("ai_os.agent_runtime.discover_enabled_tool_catalog", unavailable_catalog)
    result = run_agent_workflow(task, worker_id="worker-b")
    assert result == "Research completed using approved search result."
    assert "credible synthetic market data" in calls[1][0]
    assert "MCP tool discovery is temporarily unavailable" in calls[1][0]
    assert calls[1][1] == []
    assert [item["status"] for item in list_task_steps(task["id"])] == [
        "completed", "completed", "completed"
    ]
