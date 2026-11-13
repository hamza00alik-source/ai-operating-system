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
    expired_at = datetime.now(timezone.utc) + timedelta(seconds=20)
    assert queue.claim(agent, now=expired_at) is None
    second = queue.claim(agent, now=expired_at + timedelta(seconds=5))
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
    failed_at = datetime.now(timezone.utc)
    assert queue.fail(first, "provider_timeout", now=failed_at) == "queued"
    assert queue.claim(agent, now=failed_at + timedelta(seconds=4)) is None
    second = queue.claim(agent, now=failed_at + timedelta(seconds=5))
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

    cancelled_item = make_item("Re-admit after cancellation")
    admit(cancelled_item)
    cancelled_lease = queue.claim(agent_id)
    assert cancelled_lease is not None
    assert queue.request_cancel(
        cancelled_item.id,
        AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner",
            action="work_item.cancellation_requested",
            subject_type="work_item", subject_id=str(cancelled_item.id),
            outcome="recorded", correlation_id=str(uuid4()),
        ),
    ) == "cancellation_requested"
    assert queue.finalize_cancel(
        cancelled_lease,
        AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="worker", actor_id=str(agent_id),
            action="worker.execution_cancelled",
            subject_type="work_item", subject_id=str(cancelled_item.id),
            outcome="recorded", correlation_id=str(cancelled_lease.lease_token),
        ),
    )
    with store._lock:
        store._connection.execute(
            "UPDATE work_items SET state=? WHERE id=?",
            (TaskState.READY.value, str(cancelled_item.id)),
        )
    admit(store.get_work_item(cancelled_item.id))
    assert queue.get_entry(cancelled_item.id)["state"] == "queued"
    with store._lock:
        cancel_flag = store._connection.execute(
            "SELECT cancel_requested FROM worker_queue WHERE work_item_id=?",
            (str(cancelled_item.id),),
        ).fetchone()["cancel_requested"]
    assert cancel_flag == 0
    re_admitted = queue.claim(agent_id)
    assert re_admitted is not None and re_admitted.work_item_id == cancelled_item.id
    queue.complete(re_admitted)

    assert queue.counts() == {"done": 3}
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


def test_queue_counts_are_filtered_by_business_unit(tmp_path):
    store = SQLiteStore(tmp_path / "queue-business-scope.sqlite3")
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    agency = WorkItem(
        id=uuid4(), title="Agency task", objective="Research suppliers",
        department="intelligence-research", business_id="physical-agency",
    )
    digital = WorkItem(
        id=uuid4(), title="Digital task", objective="Research digital products",
        department="intelligence-research", business_id="digital-products",
    )
    store.save_work_item(agency)
    store.save_work_item(digital)
    queue.enqueue(agency.id, uuid4(), {"role_key": "market_intelligence_analyst"})
    queue.enqueue(digital.id, uuid4(), {"role_key": "market_intelligence_analyst"})
    assert queue.counts("physical-agency") == {"queued": 1}
    assert queue.counts("digital-products") == {"queued": 1}
    assert queue.counts() == {"queued": 2}
    with pytest.raises(ValueError, match="unknown business unit"):
        queue.counts("not-a-business")
    store.close()


def test_live_lease_can_be_renewed_but_expired_or_replaced_lease_cannot(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "renew.sqlite3", lease_seconds=10)
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {})
    start = datetime.now(timezone.utc)
    first = queue.claim(agent, now=start)
    assert first is not None

    assert queue.renew(first, now=start + timedelta(seconds=9)) is True
    # The renewed lease now expires at t+19, so it cannot be reclaimed at t+11.
    assert queue.claim(agent, now=start + timedelta(seconds=11)) is None
    assert queue.renew(first, now=start + timedelta(seconds=20)) is False

    expired_at = start + timedelta(seconds=20)
    assert queue.claim(agent, now=expired_at) is None
    replacement = queue.claim(agent, now=expired_at + timedelta(seconds=5))
    assert replacement is not None and replacement.attempt == 2
    assert queue.renew(first, now=expired_at + timedelta(seconds=6)) is False
    assert queue.renew(replacement, now=expired_at + timedelta(seconds=6)) is True
    queue.close()

def test_execution_attempt_history_records_retry_and_success(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "attempt-history.sqlite3", lease_seconds=10)
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {})
    first = queue.claim(agent)
    assert first is not None
    assert queue.list_attempts(work)[0]["status"] == "running"
    failed_at = datetime.now(timezone.utc)
    assert queue.fail(first, "TemporaryError", now=failed_at) == "queued"
    second = queue.claim(agent, now=failed_at + timedelta(seconds=5))
    assert second is not None and second.attempt == 2
    queue.complete(second)
    history = queue.list_attempts(work)
    assert [row["status"] for row in history] == ["retryable_failed", "succeeded"]
    assert history[0]["error_code"] == "TemporaryError"
    assert history[0]["finished_at"] is not None
    assert history[1]["finished_at"] is not None
    queue.close()


def test_expired_lease_is_recorded_as_interrupted_before_reclaim(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "attempt-recovery.sqlite3", lease_seconds=10)
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {})
    start = datetime.now(timezone.utc)
    first = queue.claim(agent, now=start)
    assert first is not None
    expired_at = start + timedelta(seconds=11)
    assert queue.claim(agent, now=expired_at) is None
    second = queue.claim(agent, now=expired_at + timedelta(seconds=5))
    assert second is not None and second.attempt == 2
    history = queue.list_attempts(work)
    assert [row["status"] for row in history] == ["interrupted", "running"]
    assert history[0]["finished_at"] is not None
    queue.close()


def test_retry_backoff_grows_exponentially_and_is_capped(tmp_path):
    queue = DurableWorkerQueue(
        tmp_path / "retry-backoff.sqlite3", max_attempts=5,
        retry_base_seconds=3, retry_max_seconds=10,
    )
    work, agent = uuid4(), uuid4()
    start = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)
    queue.enqueue(work, agent, {})
    first = queue.claim(agent, now=start)
    assert first is not None
    assert queue.fail(first, "temporary", now=start) == "queued"
    assert queue.claim(agent, now=start + timedelta(seconds=2)) is None
    second = queue.claim(agent, now=start + timedelta(seconds=3))
    assert second is not None and second.attempt == 2
    second_failed_at = start + timedelta(seconds=3)
    assert queue.fail(second, "temporary", now=second_failed_at) == "queued"
    assert queue.claim(agent, now=second_failed_at + timedelta(seconds=5)) is None
    third = queue.claim(agent, now=second_failed_at + timedelta(seconds=6))
    assert third is not None and third.attempt == 3
    third_failed_at = second_failed_at + timedelta(seconds=6)
    assert queue.fail(third, "temporary", now=third_failed_at) == "queued"
    # The nominal 12-second delay is capped at 10 seconds.
    assert queue.claim(agent, now=third_failed_at + timedelta(seconds=9)) is None
    fourth = queue.claim(agent, now=third_failed_at + timedelta(seconds=10))
    assert fourth is not None and fourth.attempt == 4
    queue.close()


def test_legacy_queue_database_adds_retry_column_without_losing_rows(tmp_path):
    import sqlite3

    database = tmp_path / "legacy-queue.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("""
        CREATE TABLE worker_queue (
            work_item_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('queued','leased','done','dead')),
            attempts INTEGER NOT NULL DEFAULT 0, lease_token TEXT,
            lease_expires_at TEXT, last_error TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    work, agent = uuid4(), uuid4()
    stamp = datetime.now(timezone.utc).isoformat()
    connection.execute(
        "INSERT INTO worker_queue (work_item_id,agent_id,payload_json,state,created_at,updated_at) "
        "VALUES(?,?,?,'queued',?,?)",
        (str(work), str(agent), "{}", stamp, stamp),
    )
    connection.commit()
    connection.close()

    queue = DurableWorkerQueue(database)
    entry = queue.get_entry(work)
    assert entry is not None and entry["state"] == "queued"
    assert entry["next_attempt_at"] is None
    lease = queue.claim(agent)
    assert lease is not None and lease.work_item_id == work
    queue.close()

def test_execution_history_is_secret_free_and_ordered(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "history.sqlite3")
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {"role_key": "researcher"})
    first = queue.claim(agent)
    assert first is not None
    assert queue.fail(first, "provider_timeout") == "queued"
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    second = queue.claim(agent, now=retry_at)
    assert second is not None and second.attempt == 2
    queue.complete(second)

    history = queue.list_attempts(work)
    assert [row["attempt"] for row in history] == [1, 2]
    assert [row["status"] for row in history] == ["retryable_failed", "succeeded"]
    assert history[0]["error_code"] == "provider_timeout"
    assert "lease_token" not in history[0]
    assert "payload_json" not in history[0]
    queue.close()

def test_queue_health_reports_age_expired_leases_and_dead_letters_without_secrets(tmp_path):
    queue = DurableWorkerQueue(
        tmp_path / "queue-health.sqlite3", lease_seconds=10, max_attempts=1
    )
    agent = uuid4()
    leased_work, queued_work, pending_work = uuid4(), uuid4(), uuid4()
    queue.enqueue(leased_work, agent, {"private": "never-return-this"})
    queue.enqueue(queued_work, agent, {})
    queue.enqueue(pending_work, agent, {})
    lease = queue.claim(agent)
    assert lease is not None
    queue.fail(lease, "provider_timeout")
    # Exhaust the first task to create a dead-letter entry.
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    second_lease = queue.claim(agent, now=retry_at)
    assert second_lease is not None
    queue.fail(second_lease, "provider_timeout")

    snapshot = queue.health_snapshot(now=retry_at + timedelta(seconds=11))
    assert snapshot["dead_letter_count"] == 1
    assert snapshot["queued_oldest_age_seconds"] >= 10
    assert "lease_token" not in snapshot
    assert "payload_json" not in snapshot
    queue.close()

