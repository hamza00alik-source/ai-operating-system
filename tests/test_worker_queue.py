from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from opencompany_core.worker_queue import DurableWorkerQueue, QueueError
from opencompany_core.persistence import SQLiteStore
from opencompany_core.domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem


def test_queue_claim_complete_and_duplicate_protection(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "queue.sqlite3")
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {"kind": "internal_draft"})
    with pytest.raises(QueueError):
        queue.enqueue(work, agent, {})
    lease = queue.claim(agent)
    assert lease is not None and lease.attempt == 1
    assert queue.claim(agent) is None
    queue.complete(lease)
    assert queue.counts() == {"done": 1}
    queue.close()


def test_stale_lease_cannot_complete(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "queue.sqlite3", lease_seconds=10)
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {})
    first = queue.claim(agent)
    assert first is not None
    future = datetime.now(timezone.utc) + timedelta(seconds=20)
    second = queue.claim(agent, now=future)
    assert second is not None and second.attempt == 2
    with pytest.raises(QueueError):
        queue.complete(first)
    queue.complete(second)
    queue.close()


def test_retry_limit_moves_item_to_dead_letter_state(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "queue.sqlite3", max_attempts=2)
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {})
    first = queue.claim(agent)
    assert first is not None
    assert queue.fail(first, "provider_timeout") == "queued"
    second = queue.claim(agent)
    assert second is not None and second.attempt == 2
    assert queue.fail(second, "provider_timeout") == "dead"
    assert queue.claim(agent) is None
    assert queue.counts() == {"dead": 1}
    queue.close()


def test_payload_and_configuration_are_bounded(tmp_path):
    with pytest.raises(ValueError):
        DurableWorkerQueue(tmp_path / "bad.sqlite3", max_attempts=99)
    queue = DurableWorkerQueue(tmp_path / "queue.sqlite3")
    with pytest.raises(ValueError):
        queue.enqueue(uuid4(), uuid4(), {"data": "x" * 25000})
    queue.close()


def test_shared_store_claim_is_atomic_and_expired_final_lease_dead_letters(tmp_path):
    database = tmp_path / "shared.sqlite3"
    store = SQLiteStore(database)
    now = datetime.now(timezone.utc)
    agent_id = uuid4()
    agent = AgentProfile(
        id=agent_id, name="Research Specialist", department="intelligence-research",
        purpose="Prepare evidence", capabilities=("research",), state=AgentState.ACTIVE,
        role_key="market_intelligence_analyst", team_key="intelligence-research__team_1",
    )
    store.save_agent_with_audit(agent, AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="test.agent_created", subject_type="agent_profile",
        subject_id=str(agent_id), outcome="recorded", correlation_id="test",
    ))
    item = WorkItem(
        id=uuid4(), title="Research market", objective="Prepare a sourced market report",
        department="intelligence-research", state=TaskState.QUEUED, assigned_agent_id=agent_id,
    )
    store.save_work_item_with_audit(item, AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="test.task_queued", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id="test",
    ))
    queue = DurableWorkerQueue(store._connection, lock=store._lock, max_attempts=1, lease_seconds=10)
    queue.enqueue(item.id, agent_id, {"role_key": agent.role_key})
    assert queue.available_agent_ids(now=now) == (agent_id,)
    first = queue.claim(agent_id, now=now)
    assert queue.available_agent_ids(now=now) == ()
    assert first is not None and first.attempt == 1
    assert store.get_work_item(item.id).state == TaskState.IN_PROGRESS

    future = now + timedelta(seconds=20)
    assert queue.available_agent_ids(now=future) == (agent_id,)
    assert queue.claim(agent_id, now=future) is None
    assert queue.counts() == {"dead": 1}
    assert store.get_work_item(item.id).state == TaskState.FAILED
    assert store.verify_audit_chain()
    store.close()
