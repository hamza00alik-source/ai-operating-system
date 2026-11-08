from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from ai_os.db import connect, initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision
from ai_os.service import consume_approval, create_approval, decide_approval


def _new_approval():
    return create_approval(ApprovalCreate(
        action="publish_content",
        actor_id="owner",
        resource_id="wordpress:site-1",
        action_payload={"post_id": "draft-7", "visibility": "public"},
    ))


def _consume(approval):
    return consume_approval(
        approval["id"],
        actor_id="owner",
        action="publish_content",
        resource_id="wordpress:site-1",
        action_payload={"post_id": "draft-7", "visibility": "public"},
    )


def test_concurrent_decisions_consume_approval_once(monkeypatch, tmp_path):
    database = tmp_path / "approval-test.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    approval = _new_approval()
    barrier = Barrier(2)

    def decide(value):
        barrier.wait()
        try:
            decide_approval(approval["id"], ApprovalDecision(decision=value))
            return "success"
        except ValueError:
            return "already_decided"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide, ("approved", "rejected")))

    assert outcomes.count("success") == 1
    assert outcomes.count("already_decided") == 1


def test_approval_requires_exact_action_match(monkeypatch, tmp_path):
    database = tmp_path / "approval-mismatch.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    approval = _new_approval()
    decide_approval(approval["id"], ApprovalDecision(decision="approved"))

    with pytest.raises(ValueError, match="does not match"):
        consume_approval(
            approval["id"], actor_id="owner", action="publish_content",
            resource_id="wordpress:site-1",
            action_payload={"post_id": "different-draft", "visibility": "public"},
        )


def test_approval_is_consumed_once(monkeypatch, tmp_path):
    database = tmp_path / "approval-consume.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    approval = _new_approval()
    decide_approval(approval["id"], ApprovalDecision(decision="approved"))

    consumed = _consume(approval)
    assert consumed["status"] == "consumed"
    assert consumed["consumed_at"] is not None
    with pytest.raises(ValueError, match="already been consumed"):
        _consume(approval)


def test_concurrent_consumption_allows_one_execution_attempt(monkeypatch, tmp_path):
    database = tmp_path / "approval-concurrent-consume.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    approval = _new_approval()
    decide_approval(approval["id"], ApprovalDecision(decision="approved"))
    barrier = Barrier(2)

    def consume(_):
        barrier.wait()
        try:
            _consume(approval)
            return "success"
        except ValueError:
            return "already_consumed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(consume, (1, 2)))
    assert outcomes.count("success") == 1
    assert outcomes.count("already_consumed") == 1


def test_expired_approval_cannot_be_decided_or_consumed(monkeypatch, tmp_path):
    database = tmp_path / "approval-expired.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    approval = _new_approval()
    decide_approval(approval["id"], ApprovalDecision(decision="approved"))
    with connect() as db:
        db.execute(
            "UPDATE approvals SET expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", approval["id"]),
        )
    with pytest.raises(ValueError, match="expired"):
        _consume(approval)
