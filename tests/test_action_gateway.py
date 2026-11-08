from types import SimpleNamespace

import pytest

from ai_os.action_gateway import (
    ActionGatewayError,
    clear_action_adapters_for_tests,
    execute_approved_action,
    get_action_gateway_status,
    register_action_adapter, register_agent_tool_adapter, execute_agent_tool,
)
from ai_os.approvals import create_owner_approval_request, decide_owner_approval
from ai_os.audit import list_events
from ai_os.db import connect, initialize_database
from ai_os.control_plane import initialize_control_plane, grant_capability, revoke_capability_grant
from ai_os.identity import issue_agent_token


@pytest.fixture
def gateway_db(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'action-gateway.sqlite3'}")
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "gateway-signing-key-" + "z" * 40)
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false")
    from ai_os import registry
    monkeypatch.setattr(
        registry, "get_agent",
        lambda agent_id: SimpleNamespace(id=agent_id, enabled=True, department="research"),
    )
    initialize_database()
    initialize_control_plane()
    with connect() as db:
        db.execute(
            """INSERT INTO company_runs(id,title,description,status,created_at,updated_at)
               VALUES ('gateway-run','Gateway test','Test','running',
                       '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"""
        )
    clear_action_adapters_for_tests()
    yield
    clear_action_adapters_for_tests()


def _approved_request():
    token = issue_agent_token(
        "company-orchestrator", run_id="gateway-run",
        capabilities=["approval.request"],
    )
    request = create_owner_approval_request(
        token,
        action_type="publish_product",
        parameters={
            "store": "primary-woocommerce",
            "product_id": "draft-456",
            "title": "Sample product",
            "price": "9.00",
            "currency": "USD",
        },
    )
    return decide_owner_approval(
        request["id"], action_hash=request["action_hash"], decision="approved"
    )


def _status(approval_id):
    with connect() as db:
        return db.execute(
            "SELECT status FROM owner_approval_requests WHERE id=?", (approval_id,)
        ).fetchone()["status"]


def test_disabled_gateway_does_not_consume_owner_approval(gateway_db):
    approval = _approved_request()
    with pytest.raises(ActionGatewayError, match="disabled"):
        execute_approved_action(
            approval["id"], action_type=approval["action_type"],
            parameters=approval["parameters"], execution_id="gateway-exec-1",
        )
    assert _status(approval["id"]) == "approved"


def test_missing_adapter_does_not_consume_owner_approval(gateway_db, monkeypatch):
    approval = _approved_request()
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    with pytest.raises(ActionGatewayError, match="No trusted"):
        execute_approved_action(
            approval["id"], action_type=approval["action_type"],
            parameters=approval["parameters"], execution_id="gateway-exec-2",
        )
    assert _status(approval["id"]) == "approved"


def test_gateway_consumes_exact_approval_once_and_audits_result(gateway_db, monkeypatch):
    approval = _approved_request()
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    calls = []
    register_action_adapter(
        "publish_product",
        adapter_id="test-dry-run-adapter",
        adapter=lambda parameters, execution_id: calls.append((parameters, execution_id)) or {
            "dry_run": True, "external_side_effects": False
        },
    )
    result = execute_approved_action(
        approval["id"], action_type=approval["action_type"],
        parameters=approval["parameters"], execution_id="gateway-exec-3",
    )
    assert result["status"] == "completed"
    assert result["result"]["dry_run"] is True
    assert len(calls) == 1
    assert _status(approval["id"]) == "consumed"
    with pytest.raises(ActionGatewayError, match="approved state"):
        execute_approved_action(
            approval["id"], action_type=approval["action_type"],
            parameters=approval["parameters"], execution_id="gateway-exec-4",
        )
    actions = [event["action"] for event in list_events(50)]
    assert "approved_action_execution_started" in actions
    assert "approved_action_execution_completed" in actions


def test_adapter_failure_consumes_approval_and_records_failure(gateway_db, monkeypatch):
    approval = _approved_request()
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    def fail(parameters, execution_id):
        raise RuntimeError("adapter test failure")
    register_action_adapter("publish_product", adapter_id="test-failing-adapter", adapter=fail)
    with pytest.raises(ActionGatewayError, match="after the approval was consumed"):
        execute_approved_action(
            approval["id"], action_type=approval["action_type"],
            parameters=approval["parameters"], execution_id="gateway-exec-5",
        )
    assert _status(approval["id"]) == "consumed"
    actions = [event["action"] for event in list_events(50)]
    assert "approved_action_execution_failed" in actions


def test_gateway_readiness_requires_explicit_flag_and_registered_adapter(gateway_db, monkeypatch):
    assert get_action_gateway_status()["enabled"] is False
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    assert get_action_gateway_status()["enabled"] is False
    register_action_adapter(
        "publish_product", adapter_id="test-status-adapter",
        adapter=lambda parameters, execution_id: {"dry_run": True},
    )
    status = get_action_gateway_status()
    assert status["enabled"] is True
    assert status["registered_actions"] == ["publish_product"]



def test_agent_tool_execution_requires_explicit_scoped_capability_grant(gateway_db):
    calls = []
    register_agent_tool_adapter(
        "research.search",
        capability="tool.research.read",
        adapter=lambda parameters: calls.append(parameters) or {"sources": 2},
    )

    with pytest.raises(ActionGatewayError, match="capability was denied"):
        execute_agent_tool("research-synthesist", "research.search", {"query": "demand"})
    assert calls == []

    grant = grant_capability(
        agent_id="research-synthesist",
        capability="tool.research.read",
        department_scope="research",
        granted_by="test-owner",
    )
    result = execute_agent_tool(
        "research-synthesist", "research.search", {"query": "demand"}
    )
    assert result["status"] == "completed"
    assert result["result"] == {"sources": 2}
    assert len(calls) == 1

    revoke_capability_grant(grant["grant_id"])
    with pytest.raises(ActionGatewayError, match="capability was denied"):
        execute_agent_tool("research-synthesist", "research.search", {"query": "demand"})
    assert len(calls) == 1


def test_approved_action_rejects_oversized_parameters_before_consuming_approval(gateway_db, monkeypatch):
    approval = _approved_request()
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    calls = []
    register_action_adapter(
        "publish_product", adapter_id="test-size-guard",
        adapter=lambda parameters, execution_id: calls.append(parameters) or {"ok": True},
    )
    oversized = {"payload": "x" * 65537}
    with pytest.raises(ActionGatewayError, match="64 KiB"):
        execute_approved_action(
            approval["id"], action_type=approval["action_type"],
            parameters=oversized, execution_id="gateway-size-1",
        )
    assert _status(approval["id"]) == "approved"
    assert calls == []


def test_approved_action_rejects_oversized_adapter_result_and_audits_failure(gateway_db, monkeypatch):
    approval = _approved_request()
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    register_action_adapter(
        "publish_product", adapter_id="test-large-result",
        adapter=lambda parameters, execution_id: {"payload": "x" * 65537},
    )
    with pytest.raises(ActionGatewayError, match="after the approval was consumed"):
        execute_approved_action(
            approval["id"], action_type=approval["action_type"],
            parameters=approval["parameters"], execution_id="gateway-size-2",
        )
    assert _status(approval["id"]) == "consumed"
    actions = [event["action"] for event in list_events(50)]
    assert "approved_action_execution_failed" in actions
