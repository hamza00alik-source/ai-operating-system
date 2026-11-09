import pytest
from fastapi.testclient import TestClient

from ai_os import api
from ai_os.db import connect
from ai_os.tool_approvals import (propose_tool_call, decide_tool_proposal,\n                                  reserve_approved_tool_proposal)
from ai_os.db import initialize_database
from ai_os.mcp_tool_catalog import persist_discovered_tools


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'tool-proposals.db'}")
    monkeypatch.setenv("AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST", '{"research":["research-mcp:search"]}')
    initialize_database()
    from datetime import datetime, timezone
    with connect() as db:
        db.execute("""INSERT INTO mcp_servers
            (id,name,endpoint,transport,credential_env_json,capabilities_json,enabled,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            ("research-mcp", "Research MCP", "https://mcp.example.com/mcp",
             "streamable_http", "[]", '["search"]', 1,
             datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    persist_discovered_tools("research-mcp", [{
        "name": "search", "description": "Read-only search",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}},
                         "required": ["q"], "additionalProperties": False},
    }])


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


def test_owner_approval_rechecks_current_schema(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = propose_tool_call(
        run_id="r1", task_id="t1", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    # Simulate an owner-triggered rediscovery that changes the schema.
    persist_discovered_tools("research-mcp", [{
        "name": "search",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}, "limit": {"type": "integer"}},
                         "required": ["q"], "additionalProperties": False},
    }])
    with pytest.raises(ValueError, match="schema changed"):
        decide_tool_proposal(proposal["id"], "approved")
    with connect() as db:
        row = db.execute("SELECT status FROM mcp_tool_proposals WHERE id=?", (proposal["id"],)).fetchone()
    assert row["status"] == "pending"


def test_owner_approval_rejects_disabled_server(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = propose_tool_call(
        run_id="r1", task_id="t1", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    with connect() as db:
        db.execute("UPDATE mcp_servers SET enabled=0 WHERE id='research-mcp'")
    with pytest.raises(PermissionError, match="enabled server"):
        decide_tool_proposal(proposal["id"], "approved")
    with connect() as db:
        row = db.execute("SELECT status FROM mcp_tool_proposals WHERE id=?", (proposal["id"],)).fetchone()
    assert row["status"] == "pending"



def _approved_proposal(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    proposal = propose_tool_call(
        run_id="r1", task_id="t1", department="research",
        server_id="research-mcp", tool_name="search", arguments={"q": "market"},
    )
    approved = decide_tool_proposal(proposal["id"], "approved")
    assert approved["status"] == "approved"
    return proposal


def test_approved_proposal_can_be_reserved_once_without_execution(monkeypatch, tmp_path):
    proposal = _approved_proposal(monkeypatch, tmp_path)
    reservation = reserve_approved_tool_proposal(proposal["id"])
    assert reservation["status"] == "reserved"
    assert reservation["execution_enabled"] is False
    assert reservation["remote_call_performed"] is False
    with pytest.raises(ValueError, match="already been reserved"):
        reserve_approved_tool_proposal(proposal["id"])
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM mcp_tool_execution_reservations WHERE proposal_id=?",
            (proposal["id"],),
        ).fetchall()
        audit = db.execute(
            """SELECT COUNT(*) AS n FROM audit_events
            WHERE event_type='mcp_tool_proposal.execution_reserved' AND resource_id=?""",
            (proposal["id"],),
        ).fetchone()
    assert len(rows) == 1
    assert audit["n"] == 1


def test_reservation_rejects_expired_approved_proposal(monkeypatch, tmp_path):
    proposal = _approved_proposal(monkeypatch, tmp_path)
    with connect() as db:
        db.execute(
            "UPDATE mcp_tool_proposals SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (proposal["id"],),
        )
    with pytest.raises(ValueError, match="expired"):
        reserve_approved_tool_proposal(proposal["id"])


def test_reservation_rejects_disabled_server(monkeypatch, tmp_path):
    proposal = _approved_proposal(monkeypatch, tmp_path)
    with connect() as db:
        db.execute("UPDATE mcp_servers SET enabled=0 WHERE id='research-mcp'")
    with pytest.raises(PermissionError, match="enabled server"):
        reserve_approved_tool_proposal(proposal["id"])


def test_reservation_rejects_schema_drift(monkeypatch, tmp_path):
    proposal = _approved_proposal(monkeypatch, tmp_path)
    persist_discovered_tools("research-mcp", [{
        "name": "search",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"},
                         "limit": {"type": "integer"}}, "required": ["q"],
                         "additionalProperties": False},
    }])
    with pytest.raises(ValueError, match="schema changed"):
        reserve_approved_tool_proposal(proposal["id"])


def test_reservation_rejects_fingerprint_tampering(monkeypatch, tmp_path):
    proposal = _approved_proposal(monkeypatch, tmp_path)
    with connect() as db:
        db.execute(
            "UPDATE mcp_tool_proposals SET fingerprint='tampered' WHERE id=?",
            (proposal["id"],),
        )
    with pytest.raises(ValueError, match="fingerprint integrity"):
        reserve_approved_tool_proposal(proposal["id"])



def test_owner_reservation_endpoint_records_checkpoint_only(monkeypatch, tmp_path):
    proposal = _approved_proposal(monkeypatch, tmp_path)
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(api.app) as client:
        response = client.post(
            f"/integrations/mcp/proposals/{proposal['id']}/reserve",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "reserved"
        assert response.json()["execution_enabled"] is False
        assert response.json()["remote_call_performed"] is False
        inbox = client.get("/integrations/mcp/proposals", headers=headers)
        listed = next(item for item in inbox.json() if item["id"] == proposal["id"])
        assert listed["reservation_id"] == response.json()["reservation_id"]
        replay = client.post(
            f"/integrations/mcp/proposals/{proposal['id']}/reserve",
            headers=headers,
        )
        assert replay.status_code == 409


def test_owner_reservation_endpoint_requires_auth(monkeypatch, tmp_path):
    proposal = _approved_proposal(monkeypatch, tmp_path)
    with TestClient(api.app) as client:
        response = client.post(
            f"/integrations/mcp/proposals/{proposal['id']}/reserve"
        )
        assert response.status_code == 401
