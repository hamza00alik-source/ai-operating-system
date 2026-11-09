import pytest
from datetime import datetime, timezone

from ai_os import mcp_execution as executor
from ai_os.db import connect, initialize_database
from ai_os.mcp_execution import _read_only_grants, execute_approved_proposal
from ai_os.mcp_tool_catalog import persist_discovered_tools
from ai_os.tool_approvals import decide_tool_proposal, propose_tool_call


SCHEMA = {
    "type": "object",
    "properties": {"q": {"type": "string"}},
    "required": ["q"],
    "additionalProperties": False,
}


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'mcp-execution.db'}")
    monkeypatch.setenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", '{"research":["research-mcp:search"]}')
    monkeypatch.setenv("AI_OS_MCP_READ_ONLY_TOOLS", "")
    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """INSERT INTO mcp_servers
            (id,name,endpoint,transport,credential_env_json,capabilities_json,enabled,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            ("research-mcp", "Research MCP", "https://mcp.example.com/mcp",
             "streamable_http", "[]", '["search"]', 1, now, now),
        )
    persist_discovered_tools("research-mcp", [{
        "name": "search", "description": "Read-only search", "input_schema": SCHEMA,
    }])


def _approved_proposal():
    proposal = propose_tool_call(
        run_id="run-1", task_id="task-1", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    decide_tool_proposal(proposal["id"], "approved")
    return proposal


def _mock_read_only_server(monkeypatch):
    monkeypatch.setenv("AI_OS_MCP_READ_ONLY_TOOLS", '["research-mcp:search"]')
    monkeypatch.setattr(executor, "_load_server", lambda _id: (
        {"endpoint": "https://mcp.example.com/mcp"}, object(), {}
    ))
    monkeypatch.setattr(executor, "_open_session", lambda *_args: ({}, "2025-03-26", {}))
    monkeypatch.setattr(executor, "_list_tools", lambda *_args: [{
        "name": "search", "inputSchema": SCHEMA,
        "annotations": {"readOnlyHint": True},
    }])
    monkeypatch.setattr(executor, "_post", lambda *_args: ({
        "id": "aios-owner-approved-call",
        "result": {"content": [{"type": "text", "text": "two useful sources"}]},
    }, {}))


def test_read_only_grants_are_exact_and_default_deny(monkeypatch):
    monkeypatch.delenv("AI_OS_MCP_READ_ONLY_TOOLS", raising=False)
    assert _read_only_grants() == set()
    monkeypatch.setenv("AI_OS_MCP_READ_ONLY_TOOLS", '["research-mcp:search"]')
    assert _read_only_grants() == {"research-mcp:search"}
    monkeypatch.setenv("AI_OS_MCP_READ_ONLY_TOOLS", '["search"]')
    with pytest.raises(ValueError):
        _read_only_grants()


def test_execution_requires_approved_proposal_and_explicit_read_only_grant(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = propose_tool_call(
        run_id="run-1", task_id="task-1", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    with pytest.raises(ValueError, match="approved"):
        execute_approved_proposal(proposal["id"])
    decide_tool_proposal(proposal["id"], "approved")
    with pytest.raises(PermissionError, match="AI_OS_MCP_READ_ONLY_TOOLS"):
        execute_approved_proposal(proposal["id"])
    with connect() as db:
        row = db.execute("SELECT execution_status FROM mcp_tool_proposals WHERE id=?",
                         (proposal["id"],)).fetchone()
    assert row["execution_status"] is None


def test_successful_execution_is_owner_triggered_and_cannot_be_replayed(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = _approved_proposal()
    _mock_read_only_server(monkeypatch)

    result = execute_approved_proposal(proposal["id"])
    assert result["execution_status"] == "succeeded"
    assert result["result"]["content"][0]["text"] == "two useful sources"
    with connect() as db:
        row = db.execute("SELECT execution_status FROM mcp_tool_proposals WHERE id=?",
                         (proposal["id"],)).fetchone()
        events = db.execute(
            "SELECT event_type FROM audit_events WHERE resource_id=? ORDER BY created_at",
            (proposal["id"],),
        ).fetchall()
    assert row["execution_status"] == "succeeded"
    assert [event["event_type"] for event in events] == [
        "mcp_tool.execution_started", "mcp_tool.execution_succeeded"
    ]
    with pytest.raises(ValueError, match="already been consumed"):
        execute_approved_proposal(proposal["id"])


def test_tampered_approved_arguments_are_rejected_before_network(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = _approved_proposal()
    with connect() as db:
        db.execute("UPDATE mcp_tool_proposals SET arguments_json=? WHERE id=?",
                   ('{"q":"tampered"}', proposal["id"]))
    monkeypatch.setenv("AI_OS_MCP_READ_ONLY_TOOLS", '["research-mcp:search"]')
    with pytest.raises(PermissionError, match="fingerprint"):
        execute_approved_proposal(proposal["id"])
    with connect() as db:
        row = db.execute("SELECT execution_status FROM mcp_tool_proposals WHERE id=?",
                         (proposal["id"],)).fetchone()
    assert row["execution_status"] is None
