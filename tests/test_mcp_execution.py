import pytest

from ai_os.db import initialize_database
from ai_os.mcp_execution import _read_only_grants, execute_approved_proposal
from ai_os.mcp_tool_catalog import persist_discovered_tools
from ai_os.tool_approvals import propose_tool_call, decide_tool_proposal
from ai_os.db import connect
from datetime import datetime, timezone


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
        "name": "search", "description": "Read-only search",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}},
                         "required": ["q"], "additionalProperties": False},
    }])


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


def test_approved_execution_cannot_be_replayed(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = propose_tool_call(
        run_id="run-2", task_id="task-2", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    decide_tool_proposal(proposal["id"], "approved")
    # A malformed/absent grant blocks before the execution attempt is consumed.
    monkeypatch.setenv("AI_OS_MCP_READ_ONLY_TOOLS", "[]")
    with pytest.raises(PermissionError):
        execute_approved_proposal(proposal["id"])
    monkeypatch.setenv("AI_OS_MCP_READ_ONLY_TOOLS", '["research-mcp:search"]')
    # With a grant, the executor consumes the approval before making any network call.
    # Missing credentials/network are expected to fail closed and mark the attempt failed.
    with pytest.raises((RuntimeError, ValueError)):
        execute_approved_proposal(proposal["id"])
    with connect() as db:
        row = db.execute("SELECT execution_status FROM mcp_tool_proposals WHERE id=?",
                         (proposal["id"],)).fetchone()
    assert row["execution_status"] in {"failed", "running"}
    with pytest.raises(ValueError, match="already been consumed"):
        execute_approved_proposal(proposal["id"])
