import pytest
from fastapi.testclient import TestClient

from ai_os import api
from ai_os.db import connect
from ai_os.tool_approvals import propose_tool_call, decide_tool_proposal


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'tool-proposals.db'}")
    monkeypatch.setenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", '{"research":["research-mcp:search"]}')


def test_tool_proposal_requires_department_allowlist_and_is_not_executed(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    with pytest.raises(PermissionError):
        propose_tool_call(run_id="r1", task_id="t1", department="marketing",
                          server_id="research-mcp", tool_name="search", arguments={"q": "x"})
    proposal = propose_tool_call(
        run_id="r1", task_id="t1", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    assert proposal["status"] == "pending"
    assert proposal["execution_enabled"] is False
    with connect() as db:
        row = db.execute("SELECT status, fingerprint FROM mcp_tool_proposals WHERE id=?",
                         (proposal["id"],)).fetchone()
    assert row["status"] == "pending"
    assert row["fingerprint"] == proposal["fingerprint"]


def test_owner_decision_is_one_time_and_does_not_execute(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = propose_tool_call(
        run_id="r1", task_id="t1", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(api.app) as client:
        inbox = client.get("/integrations/mcp/proposals", headers=headers)
        assert inbox.status_code == 200
        assert inbox.json()[0]["id"] == proposal["id"]
        decision = client.post(
            f"/integrations/mcp/proposals/{proposal['id']}/decision",
            headers=headers, json={"decision": "approved"},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "approved"
        assert decision.json()["execution_enabled"] is False
        replay = client.post(
            f"/integrations/mcp/proposals/{proposal['id']}/decision",
            headers=headers, json={"decision": "approved"},
        )
        assert replay.status_code == 409


def test_tool_proposal_inbox_requires_owner_auth(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    with TestClient(api.app) as client:
        assert client.get("/integrations/mcp/proposals").status_code == 401


def test_tool_proposal_arguments_are_bounded(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="64 KiB"):
        propose_tool_call(run_id="r1", task_id="t1", department="research",
                          server_id="research-mcp", tool_name="search",
                          arguments={"q": "x" * 70000})
