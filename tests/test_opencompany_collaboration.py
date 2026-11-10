from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from opencompany_core.collaboration import (
    AgentHandoff, HandoffState, accept_handoff, cancel_handoff,
    decline_handoff, deliver_handoff,
)


def handoff():
    now = datetime.now(timezone.utc)
    return AgentHandoff(
        id=uuid4(), work_item_id=uuid4(), sender_agent_id=uuid4(),
        recipient_agent_id=uuid4(), purpose="Independent quality review",
        requested_result="Return findings with evidence references",
        context="Review the attached deliverable against the stated acceptance criteria.",
        created_at=now, updated_at=now,
    )


def test_handoff_requires_distinct_agents():
    agent = uuid4()
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="distinct agents"):
        AgentHandoff(uuid4(), uuid4(), agent, agent, "Review", "Findings",
                     "Bounded context", created_at=now, updated_at=now)


def test_handoff_must_be_accepted_before_delivery():
    request = handoff()
    with pytest.raises(ValueError, match="only accepted"):
        deliver_handoff(request, response_artifact_ids=(uuid4(),),
                        at=request.created_at + timedelta(seconds=1))


def test_handoff_lifecycle_records_result_artifact():
    request = handoff()
    accepted = accept_handoff(request, at=request.created_at + timedelta(seconds=1))
    artifact_id = uuid4()
    delivered = deliver_handoff(
        accepted, response_artifact_ids=(artifact_id,),
        at=accepted.updated_at + timedelta(seconds=1),
    )
    assert delivered.state is HandoffState.DELIVERED
    assert delivered.response_artifact_ids == (artifact_id,)


def test_declined_handoff_cannot_be_accepted():
    request = handoff()
    declined = decline_handoff(request, at=request.created_at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="only proposed"):
        accept_handoff(declined, at=declined.updated_at + timedelta(seconds=1))


def test_open_handoff_can_be_cancelled():
    request = handoff()
    cancelled = cancel_handoff(request, at=request.created_at + timedelta(seconds=1))
    assert cancelled.state is HandoffState.CANCELLED


def test_delivered_handoff_requires_output_artifact():
    request = handoff()
    accepted = accept_handoff(request, at=request.created_at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="at least one"):
        deliver_handoff(accepted, response_artifact_ids=(),
                        at=accepted.updated_at + timedelta(seconds=1))


def test_handoff_rejects_non_monotonic_event_time():
    request = handoff()
    with pytest.raises(ValueError, match="cannot precede"):
        accept_handoff(request, at=request.created_at - timedelta(seconds=1))
