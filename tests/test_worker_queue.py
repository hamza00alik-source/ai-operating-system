from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from opencompany_core.worker_queue import DurableWorkerQueue, QueueError
from opencompany_core.persistence import SQLiteStore
from opencompany_core.domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.delegation_records import DelegationRepository


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


def test_authorized_re_admission_reuses_done_and_dead_queue_rows(tmp_path):
    store = SQLiteStore(tmp_path / "re_admission.sqlite3")
    agent_id = uuid4()
    agent = AgentProfile(
        id=agent_id, name="Research Specialist", department="intelligence-research",
        purpose="Prepare evidence", capabilities=("research",), state=AgentState.ACTIVE,
        role_key="market_intelligence_analyst", team_key="intelligence-research__team_1",
    )
    store.save_agent(agent)
    queue = DurableWorkerQueue(
        store._connection, lock=store._lock, max_attempts=1, lease_seconds=30,
    )

    def make_item(title):
        item = WorkItem(
            id=uuid4(), title=title, objective="Prepare an internal draft",
            department="intelligence-research", state=TaskState.READY,
            assigned_agent_id=agent_id,
        )
        store.save_work_item(item)
        return item

    def admit(item):
        queue.enqueue_authorized(
            item, agent_id, {"role_key": agent.role_key, "team_key": agent.team_key},
            AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                actor_type="owner", actor_id="owner", action="work_item.queued",
                subject_type="work_item", subject_id=str(item.id),
                outcome="recorded", correlation_id=str(uuid4()),
            ),
        )

    completed_item = make_item("Retry after review")
    admit(completed_item)
    first = queue.claim(agent_id)
    assert first is not None
    queue.complete(first)
    with store._lock:
        store._connection.execute(
            "UPDATE work_items SET state=? WHERE id=?",
            (TaskState.READY.value, str(completed_item.id)),
        )
    admit(store.get_work_item(completed_item.id))
    second = queue.claim(agent_id)
    assert second is not None and second.work_item_id == completed_item.id
    assert second.attempt == 1
    queue.complete(second)

    failed_item = make_item("Retry after failure")
    admit(failed_item)
    failed_attempt = queue.claim(agent_id)
    assert failed_attempt is not None
    assert queue.fail(failed_attempt, "provider_unavailable") == "dead"
    with store._lock:
        store._connection.execute(
            "UPDATE work_items SET state=? WHERE id=?",
            (TaskState.READY.value, str(failed_item.id)),
        )
    admit(store.get_work_item(failed_item.id))
    retried = queue.claim(agent_id)
    assert retried is not None and retried.work_item_id == failed_item.id
    assert retried.attempt == 1
    queue.complete(retried)
    assert queue.counts() == {"done": 2}
    assert store.verify_audit_chain()
    store.close()


def test_delegated_child_can_be_re_admitted_after_review_revision(tmp_path):
    store = SQLiteStore(tmp_path / "delegated_re_admission.sqlite3")
    delegations = DelegationRepository(store._connection, store._lock)
    agent_id = uuid4()
    agent = AgentProfile(
        id=agent_id, name="Research Specialist", department="intelligence-research",
        purpose="Prepare evidence", capabilities=("research",), state=AgentState.ACTIVE,
        role_key="market_intelligence_analyst", team_key="intelligence-research__team_1",
    )
    store.save_agent(agent)
    parent_id = uuid4()
    proposal = delegations.create_proposal(
        parent_work_item_id=parent_id,
        request={"required_capabilities": ["market_research"]},
        manager_agent_id=None, mode="specialist_team",
        team_key=agent.team_key,
        children=[{
            "assigned_agent_id": str(agent_id), "role_key": agent.role_key,
            "team_key": agent.team_key, "title": "Research child",
            "objective": "Prepare a sourced internal research draft",
        }],
    )
    child_id = UUID(proposal["children"][0]["id"])
    with store._lock:
        store._connection.execute(
            "UPDATE delegation_child_tasks SET state='approved' WHERE id=?",
            (str(child_id),),
        )
    item = WorkItem(
        id=child_id, title="Research child", objective="Prepare a sourced internal research draft",
        department="intelligence-research", state=TaskState.READY,
        assigned_agent_id=agent_id,
    )
    store.save_work_item(item)
    queue = DurableWorkerQueue(store._connection, lock=store._lock, lease_seconds=30)

    def admit():
        queue.enqueue_authorized(
            store.get_work_item(child_id), agent_id,
            {"role_key": agent.role_key, "team_key": agent.team_key},
            AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                actor_type="owner", actor_id="owner", action="work_item.queued",
                subject_type="work_item", subject_id=str(child_id),
                outcome="recorded", correlation_id=str(uuid4()),
            ),
        )

    admit()
    first = queue.claim(agent_id)
    assert first is not None
    queue.complete(first)
    with store._lock:
        store._connection.execute(
            "UPDATE work_items SET state=? WHERE id=?",
            (TaskState.READY.value, str(child_id)),
        )
    # The delegation record remains queued after its first admission. A revision
    # must still be re-admittable once the durable queue row is terminal.
    admit()
    second = queue.claim(agent_id)
    assert second is not None and second.work_item_id == child_id
    queue.complete(second)
    assert store.verify_audit_chain()
    store.close()
