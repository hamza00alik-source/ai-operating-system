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
    second = queue.claim(agent, now=future + timedelta(seconds=10))
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
    second = queue.claim(agent, now=datetime.now(timezone.utc) + timedelta(seconds=10))
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

    replacement = queue.claim(agent, now=start + timedelta(seconds=30))
    assert replacement is not None and replacement.attempt == 2
    assert queue.renew(first, now=start + timedelta(seconds=21)) is False
    assert queue.renew(replacement, now=start + timedelta(seconds=31)) is True
    queue.close()



def test_standalone_queue_dead_letters_expired_final_lease_without_core_tables(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "standalone-expiry.sqlite3", max_attempts=1, lease_seconds=10)
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {})
    start = datetime.now(timezone.utc)
    first = queue.claim(agent, now=start)
    assert first is not None
    assert queue.claim(agent, now=start + timedelta(seconds=20)) is None
    assert queue.counts() == {"dead": 1}
    queue.close()


def test_expired_lease_cannot_be_completed_even_before_reclaim(tmp_path):
    queue = DurableWorkerQueue(tmp_path / "expired-finish.sqlite3", lease_seconds=10)
    work, agent = uuid4(), uuid4()
    queue.enqueue(work, agent, {})
    lease = queue.claim(agent)
    assert lease is not None
    with queue._lock:
        queue._db.execute(
            "UPDATE worker_queue SET lease_expires_at=? WHERE work_item_id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), str(work)),
        )
    with pytest.raises(QueueError, match="stale"):
        queue.complete(lease)
    with pytest.raises(QueueError, match="stale"):
        queue.fail(lease, "late_failure")
    queue.close()


def test_shared_queue_does_not_lease_work_for_deactivated_agent(tmp_path):
    store = SQLiteStore(tmp_path / "deactivated-agent.sqlite3")
    agent_id = uuid4()
    agent = AgentProfile(
        id=agent_id, name="Research Specialist", department="intelligence-research",
        purpose="Prepare evidence", capabilities=("research",), state=AgentState.ACTIVE,
        role_key="market_intelligence_analyst", team_key="intelligence-research__team_1",
    )
    store.save_agent(agent)
    item = WorkItem(
        id=uuid4(), title="Queued research", objective="Prepare an internal draft",
        department="intelligence-research", state=TaskState.QUEUED,
        assigned_agent_id=agent_id,
    )
    store.save_work_item(item)
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    queue.enqueue(item.id, agent_id, {"role_key": agent.role_key})
    with store._lock:
        store._connection.execute(
            "UPDATE agent_profiles SET state='paused' WHERE id=?", (str(agent_id),)
        )
    assert queue.claim(agent_id) is None
    assert queue.counts() == {"queued": 1}
    assert store.get_work_item(item.id).state == TaskState.QUEUED
    store.close()


def test_owner_reassignment_updates_task_queue_and_audit_atomically(tmp_path):
    store = SQLiteStore(tmp_path / "reassign.sqlite3")
    old_id, new_id = uuid4(), uuid4()
    for agent_id, name in ((old_id, "Old Researcher"), (new_id, "New Researcher")):
        store.save_agent(AgentProfile(
            id=agent_id, name=name, department="intelligence-research",
            purpose="Prepare evidence", capabilities=("research",),
            state=AgentState.ACTIVE, role_key="market_intelligence_analyst",
            team_key="intelligence-research__team_1",
        ))
    item = WorkItem(
        id=uuid4(), title="Queued research", objective="Prepare a sourced internal report",
        department="intelligence-research", state=TaskState.READY,
        assigned_agent_id=old_id, business_id="physical-agency",
    )
    store.save_work_item(item)
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    queue.enqueue_authorized(item, old_id, {
        "role_key": "market_intelligence_analyst",
        "team_key": "intelligence-research__team_1",
        "kind": "internal_draft",
    }, AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="work_item.queued", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id="queue",
    ))
    result = queue.reassign_queued_work_item(item.id, new_id, AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="work_item.reassigned", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id="reassign",
        details={"from": str(old_id), "to": str(new_id)},
    ), expected_current_agent_id=old_id)
    assert result["previous_agent_id"] == str(old_id)
    assert result["assigned_agent_id"] == str(new_id)
    assert store.get_work_item(item.id).assigned_agent_id == new_id
    entry = queue.get_entry(item.id)
    assert entry["agent_id"] == str(new_id) and entry["state"] == "queued"
    lease = queue.claim(new_id)
    assert lease is not None and lease.work_item_id == item.id
    assert lease.payload["role_key"] == "market_intelligence_analyst"
    assert store.verify_audit_chain()
    store.close()


def test_reassignment_rejects_leased_and_delegated_work(tmp_path):
    store = SQLiteStore(tmp_path / "reassign-gates.sqlite3")
    old_id, new_id = uuid4(), uuid4()
    for agent_id, name in ((old_id, "Old Researcher"), (new_id, "New Researcher")):
        store.save_agent(AgentProfile(
            id=agent_id, name=name, department="intelligence-research",
            purpose="Prepare evidence", capabilities=("research",),
            state=AgentState.ACTIVE, role_key="market_intelligence_analyst",
            team_key="intelligence-research__team_1",
        ))
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    def record(action, subject):
        return AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
            actor_id="owner", action=action, subject_type="work_item",
            subject_id=str(subject), outcome="recorded", correlation_id=str(uuid4()),
        )
    leased = WorkItem(
        id=uuid4(), title="Leased research", objective="Prepare report",
        department="intelligence-research", state=TaskState.READY, assigned_agent_id=old_id,
    )
    store.save_work_item(leased)
    queue.enqueue_authorized(leased, old_id, {"role_key": "market_intelligence_analyst",
        "team_key": "intelligence-research__team_1"}, record("work_item.queued", leased.id))
    assert queue.claim(old_id) is not None
    with pytest.raises(QueueError, match="only pending work"):
        queue.reassign_queued_work_item(leased.id, new_id, record("work_item.reassigned", leased.id), expected_current_agent_id=old_id)
    assert store.get_work_item(leased.id).assigned_agent_id == old_id

    delegated_id = uuid4()
    with store._lock:
        store._connection.execute(
            """INSERT INTO delegation_child_tasks
               (id,proposal_id,parent_work_item_id,assigned_agent_id,role_key,team_key,title,objective,state,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (str(delegated_id), str(uuid4()), str(uuid4()), str(old_id),
             "market_intelligence_analyst", "intelligence-research__team_1",
             "Delegated child", "Approved objective", "queued", datetime.now(timezone.utc).isoformat()),
        )
    delegated = WorkItem(
        id=delegated_id, title="Delegated child", objective="Approved objective",
        department="intelligence-research", state=TaskState.READY, assigned_agent_id=old_id,
    )
    store.save_work_item(delegated)
    queue.enqueue_authorized(delegated, old_id, {"role_key": "market_intelligence_analyst",
        "team_key": "intelligence-research__team_1"}, record("work_item.queued", delegated.id))
    with pytest.raises(QueueError, match="new approved delegation"):
        queue.reassign_queued_work_item(delegated.id, new_id, record("work_item.reassigned", delegated.id), expected_current_agent_id=old_id)
    assert store.get_work_item(delegated.id).assigned_agent_id == old_id
    assert queue.get_entry(delegated.id)["agent_id"] == str(old_id)
    assert store.verify_audit_chain()
    store.close()


def test_reassignment_rolls_back_both_records_when_audit_append_fails(tmp_path):
    store = SQLiteStore(tmp_path / "reassign-audit-rollback.sqlite3")
    old_id, new_id = uuid4(), uuid4()
    for agent_id, name in ((old_id, "Old Researcher"), (new_id, "New Researcher")):
        store.save_agent(AgentProfile(
            id=agent_id, name=name, department="intelligence-research",
            purpose="Prepare evidence", capabilities=("research",),
            state=AgentState.ACTIVE, role_key="market_intelligence_analyst",
            team_key="intelligence-research__team_1",
        ))
    item = WorkItem(
        id=uuid4(), title="Queued research", objective="Prepare report",
        department="intelligence-research", state=TaskState.READY, assigned_agent_id=old_id,
    )
    store.save_work_item(item)
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    admission_event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="work_item.queued", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id="admission",
    )
    queue.enqueue_authorized(item, old_id, {
        "role_key": "market_intelligence_analyst",
        "team_key": "intelligence-research__team_1",
    }, admission_event)
    # Reusing an existing audit ID forces the append to fail after both UPDATEs.
    with pytest.raises(Exception):
        queue.reassign_queued_work_item(item.id, new_id, AuditRecord(
            id=admission_event.id, occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="work_item.reassigned",
            subject_type="work_item", subject_id=str(item.id), outcome="recorded",
            correlation_id="duplicate-audit",
        ), expected_current_agent_id=old_id)
    assert store.get_work_item(item.id).assigned_agent_id == old_id
    entry = queue.get_entry(item.id)
    assert entry["agent_id"] == str(old_id) and entry["state"] == "queued"
    assert store.verify_audit_chain()
    store.close()


def test_reassignment_rejects_inactive_or_cross_department_target(tmp_path):
    store = SQLiteStore(tmp_path / "reassign-target-gates.sqlite3")
    old_id, paused_id, wrong_department_id = uuid4(), uuid4(), uuid4()
    store.save_agent(AgentProfile(
        id=old_id, name="Current Researcher", department="intelligence-research",
        purpose="Research", capabilities=("research",), state=AgentState.ACTIVE,
        role_key="market_intelligence_analyst", team_key="intelligence-research__team_1",
    ))
    store.save_agent(AgentProfile(
        id=paused_id, name="Paused Researcher", department="intelligence-research",
        purpose="Research", capabilities=("research",), state=AgentState.PAUSED,
        role_key="market_intelligence_analyst", team_key="intelligence-research__team_1",
    ))
    store.save_agent(AgentProfile(
        id=wrong_department_id, name="Engineer", department="engineering-ai-systems",
        purpose="Build systems", capabilities=("engineering",), state=AgentState.ACTIVE,
        role_key="software_engineering_lead", team_key="management",
    ))
    item = WorkItem(
        id=uuid4(), title="Queued research", objective="Prepare report",
        department="intelligence-research", state=TaskState.READY, assigned_agent_id=old_id,
    )
    store.save_work_item(item)
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    queue.enqueue_authorized(item, old_id, {"role_key": "market_intelligence_analyst",
        "team_key": "intelligence-research__team_1"}, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
            actor_id="owner", action="work_item.queued", subject_type="work_item",
            subject_id=str(item.id), outcome="recorded", correlation_id="admission",
        ))
    def reassignment_record():
        return AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
            actor_id="owner", action="work_item.reassigned", subject_type="work_item",
            subject_id=str(item.id), outcome="recorded", correlation_id=str(uuid4()),
        )
    with pytest.raises(QueueError, match="active, role-assigned"):
        queue.reassign_queued_work_item(item.id, paused_id, reassignment_record(), expected_current_agent_id=old_id)
    with pytest.raises(QueueError, match="active, role-assigned"):
        queue.reassign_queued_work_item(item.id, wrong_department_id, reassignment_record(), expected_current_agent_id=old_id)
    assert store.get_work_item(item.id).assigned_agent_id == old_id
    assert queue.get_entry(item.id)["agent_id"] == str(old_id)
    assert store.verify_audit_chain()
    store.close()


def test_reassignment_recovers_unleased_in_progress_retry_to_queued(tmp_path):
    store = SQLiteStore(tmp_path / "reassign-recovery.sqlite3")
    old_id, new_id = uuid4(), uuid4()
    for agent_id, name in ((old_id, "Old Researcher"), (new_id, "New Researcher")):
        store.save_agent(AgentProfile(
            id=agent_id, name=name, department="intelligence-research",
            purpose="Prepare evidence", capabilities=("research",),
            state=AgentState.ACTIVE, role_key="market_intelligence_analyst",
            team_key="intelligence-research__team_1",
        ))
    item = WorkItem(
        id=uuid4(), title="Interrupted research", objective="Prepare report",
        department="intelligence-research", state=TaskState.READY, assigned_agent_id=old_id,
    )
    store.save_work_item(item)
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    queue.enqueue_authorized(item, old_id, {"role_key": "market_intelligence_analyst",
        "team_key": "intelligence-research__team_1"}, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
            actor_id="owner", action="work_item.queued", subject_type="work_item",
            subject_id=str(item.id), outcome="recorded", correlation_id="recovery-admission",
        ))
    # Model the runner's retry state after a lease has been released.
    with store._lock:
        store._connection.execute(
            "UPDATE work_items SET state=? WHERE id=?",
            (TaskState.IN_PROGRESS.value, str(item.id)),
        )
    result = queue.reassign_queued_work_item(item.id, new_id, AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="work_item.reassigned", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id="recovery-reassign",
        details={"previous_state": "in_progress"},
    ), expected_current_agent_id=old_id)
    assert result["previous_state"] == TaskState.IN_PROGRESS.value
    recovered = store.get_work_item(item.id)
    assert recovered.state == TaskState.QUEUED
    assert recovered.assigned_agent_id == new_id
    lease = queue.claim(new_id)
    assert lease is not None and lease.work_item_id == item.id
    assert store.get_work_item(item.id).state == TaskState.IN_PROGRESS
    assert store.verify_audit_chain()
    store.close()


def test_queue_health_snapshot_reports_age_expired_leases_and_dead_letters_without_secrets(tmp_path):
    queue = DurableWorkerQueue(
        tmp_path / "health.sqlite3", lease_seconds=10, max_attempts=1
    )
    queued_agent, active_agent, dead_agent = uuid4(), uuid4(), uuid4()
    queue.enqueue(uuid4(), queued_agent, {"private": "never-return-this"})
    queue.enqueue(uuid4(), active_agent, {})
    active_lease = queue.claim(active_agent)
    assert active_lease is not None
    queue.enqueue(uuid4(), dead_agent, {})
    dead_lease = queue.claim(dead_agent)
    assert dead_lease is not None
    assert queue.fail(dead_lease, "provider_timeout") == "dead"

    observed = datetime.now(timezone.utc) + timedelta(seconds=20)
    snapshot = queue.health_snapshot(now=observed)
    assert snapshot["counts"]["queued"] == 1
    assert snapshot["counts"]["leased"] == 1
    assert snapshot["dead_letter_count"] == 1
    assert snapshot["expired_leases"] == 1
    assert snapshot["queued_oldest_age_seconds"] >= 20
    assert "lease_token" not in str(snapshot)
    assert "payload_json" not in str(snapshot)
    assert "never-return-this" not in str(snapshot)
    queue.close()


# Durable retry, interrupted-attempt, and checkpoint observability regressions.

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
    start = datetime.now(timezone.utc) + timedelta(seconds=30)
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
    expired_agent, expired_work = uuid4(), uuid4()
    queue.enqueue(expired_work, expired_agent, {})
    expired_lease = queue.claim(
        expired_agent, now=retry_at + timedelta(seconds=11)
    )
    assert expired_lease is not None

    snapshot = queue.health_snapshot(now=retry_at + timedelta(seconds=22))
    assert snapshot["dead_letter_count"] == 2
    assert snapshot["expired_leases"] == 1
    assert snapshot["queued_oldest_age_seconds"] >= 10
    assert "lease_token" not in snapshot
    assert "payload_json" not in snapshot
    queue.close()
