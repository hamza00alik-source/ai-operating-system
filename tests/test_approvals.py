import pytest

from ai_os.approvals import (
    ApprovalSecurityError,
    consume_owner_approval,
    create_owner_approval_request,
    decide_owner_approval,
)
from ai_os.db import initialize_database
from ai_os.identity import issue_agent_token


@pytest.fixture
def approval_db(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'approvals.db'}")
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    from types import SimpleNamespace
    monkeypatch.setattr(
        "ai_os.registry.get_agent",
        lambda agent_id: SimpleNamespace(id=agent_id, enabled=True),
    )
    initialize_database()


def _ceo_token(run_id="run-approval-1"):
    return issue_agent_token(
        "company-orchestrator",
        run_id=run_id,
        capabilities=["approval.request"],
    )


def _request(token=None):
    return create_owner_approval_request(
        token or _ceo_token(),
        action_type="publish_product",
        parameters={
            "store": "primary-woocommerce",
            "product_id": "draft-123",
            "title": "Example digital product",
            "price": "9.00",
            "currency": "USD",
        },
    )


def test_ceo_can_create_exact_scope_pending_approval(approval_db):
    request = _request()
    assert request["status"] == "pending"
    assert request["requested_by"] == "company-orchestrator"
    assert request["run_id"] == "run-approval-1"
    assert request["parameters"]["product_id"] == "draft-123"
    assert len(request["action_hash"]) == 64


def test_specialist_cannot_create_owner_approval(approval_db):
    token = issue_agent_token(
        "marketing-content-creator",
        run_id="run-approval-1",
        capabilities=["step.report"],
    )
    with pytest.raises(ApprovalSecurityError):
        create_owner_approval_request(
            token,
            action_type="publish_product",
            parameters={"product_id": "draft-123"},
        )


def test_caller_cannot_mint_unapproved_capability(approval_db):
    with pytest.raises(Exception, match="not granted"):
        issue_agent_token(
            "marketing-content-creator",
            run_id="run-approval-1",
            capabilities=["approval.request"],
        )


def test_owner_decision_requires_exact_hash_and_is_one_time(approval_db):
    request = _request()
    with pytest.raises(ApprovalSecurityError, match="exact action hash"):
        decide_owner_approval(request["id"], action_hash="0" * 64, decision="approved")
    approved = decide_owner_approval(
        request["id"], action_hash=request["action_hash"], decision="approved"
    )
    assert approved["status"] == "approved"
    with pytest.raises(ApprovalSecurityError, match="no longer pending"):
        decide_owner_approval(
            request["id"], action_hash=request["action_hash"], decision="approved"
        )


def test_execution_must_match_exact_approved_parameters_and_consume_once(approval_db):
    request = _request()
    decide_owner_approval(
        request["id"], action_hash=request["action_hash"], decision="approved"
    )
    changed = dict(request["parameters"], price="19.00")
    with pytest.raises(ApprovalSecurityError, match="do not match"):
        consume_owner_approval(
            request["id"],
            action_type="publish_product",
            parameters=changed,
            execution_id="exec-1",
        )
    consumed = consume_owner_approval(
        request["id"],
        action_type="publish_product",
        parameters=request["parameters"],
        execution_id="exec-1",
    )
    assert consumed["status"] == "consumed"
    assert consumed["execution_id"] == "exec-1"
    with pytest.raises(ApprovalSecurityError, match="approved state"):
        consume_owner_approval(
            request["id"],
            action_type="publish_product",
            parameters=request["parameters"],
            execution_id="exec-2",
        )


def test_rejected_approval_cannot_be_consumed(approval_db):
    request = _request()
    decide_owner_approval(
        request["id"], action_hash=request["action_hash"], decision="rejected"
    )
    with pytest.raises(ApprovalSecurityError, match="approved state"):
        consume_owner_approval(
            request["id"],
            action_type="publish_product",
            parameters=request["parameters"],
            execution_id="exec-rejected",
        )


def test_unknown_actions_and_non_json_parameters_are_rejected(approval_db):
    token = _ceo_token()
    with pytest.raises(ApprovalSecurityError, match="allowlist"):
        create_owner_approval_request(
            token, action_type="run_shell", parameters={"command": "echo unsafe"}
        )
    with pytest.raises(ApprovalSecurityError, match="finite JSON"):
        create_owner_approval_request(
            token, action_type="publish_product", parameters={"price": float("nan")}
        )


def test_expired_approval_is_marked_expired_and_cannot_be_consumed(approval_db, monkeypatch):
    request = _request()
    decide_owner_approval(
        request["id"], action_hash=request["action_hash"], decision="approved"
    )
    monkeypatch.setattr("ai_os.approvals.time.time", lambda: request["expires_at"] + 1)
    with pytest.raises(ApprovalSecurityError, match="expired"):
        consume_owner_approval(
            request["id"],
            action_type="publish_product",
            parameters=request["parameters"],
            execution_id="exec-expired",
        )
    from ai_os.db import connect
    with connect() as db:
        row = db.execute(
            "SELECT status FROM owner_approval_requests WHERE id=?", (request["id"],)
        ).fetchone()
    assert row["status"] == "expired"
