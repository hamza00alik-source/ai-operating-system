from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from opencompany_core.domain import (
    AgentProfile, AgentState, ApprovalDecision, ApprovalState,
    AttemptState, AuditRecord, ExecutionAttempt, TaskState, WorkArtifact,
    WorkItem,
)


def test_work_item_rejects_self_dependency():
    item_id = uuid4()
    with pytest.raises(ValueError, match="cannot depend on itself"):
        WorkItem(item_id, "Prepare report", "Produce a sourced report", "research",
                 depends_on=(item_id,))


def test_work_item_requires_utc_timestamp():
    with pytest.raises(ValueError, match="must be expressed in UTC"):
        WorkItem(uuid4(), "Prepare report", "Produce a sourced report", "research",
                 created_at=datetime.now(timezone(timedelta(hours=5))))


def test_running_attempt_requires_start_time():
    with pytest.raises(ValueError, match="require started_at"):
        ExecutionAttempt(uuid4(), uuid4(), 1, AttemptState.RUNNING)


def test_terminal_attempt_requires_finish_time():
    with pytest.raises(ValueError, match="require finished_at"):
        ExecutionAttempt(uuid4(), uuid4(), 1, AttemptState.SUCCEEDED,
                         started_at=datetime.now(timezone.utc))


def test_failed_attempt_requires_failure_code():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="require a failure_code"):
        ExecutionAttempt(uuid4(), uuid4(), 1, AttemptState.FAILED,
                         started_at=now, finished_at=now)


def test_approved_action_requires_recorded_decision():
    with pytest.raises(ValueError, match="require decided_at and decided_by"):
        ApprovalDecision(uuid4(), "publish_listing", "listing", "listing-1", "owner",
                         state=ApprovalState.APPROVED)


def test_agent_profile_requires_capabilities():
    with pytest.raises(ValueError, match="capabilities"):
        AgentProfile(uuid4(), "Research Analyst", "research", "Find evidence", ())


def test_artifact_requires_locator():
    with pytest.raises(ValueError, match="locator"):
        WorkArtifact(uuid4(), uuid4(), "Report", "text/markdown", "")


def test_audit_record_requires_correlation_id():
    with pytest.raises(ValueError, match="correlation_id"):
        AuditRecord(uuid4(), datetime.now(timezone.utc), "owner", "owner-1",
                    "task.created", "work_item", "task-1", "accepted", "")


def test_valid_completed_work_item_contract():
    item = WorkItem(uuid4(), "Prepare report", "Produce a sourced report", "research",
                    state=TaskState.COMPLETED)
    assert item.state is TaskState.COMPLETED
