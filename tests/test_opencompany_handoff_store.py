from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from opencompany_core.collaboration import AgentHandoff, HandoffState, accept_handoff
from opencompany_core.collaboration_store import HandoffRepository
from opencompany_core.domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore


def _event(action, subject_type, subject_id):
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type=subject_type, subject_id=str(subject_id),
        outcome="recorded", correlation_id=str(uuid4()),
    )


def test_handoff_is_persisted_and_transition_is_audited(tmp_path):
    store = SQLiteStore(tmp_path / "handoffs.sqlite3")
    repository = HandoffRepository(store._connection, store._lock)
    sender_id, recipient_id = uuid4(), uuid4()
    for agent_id, name, role in (
        (sender_id, "Research Sender", "market_demand_researcher"),
        (recipient_id, "Research Recipient", "competitor_intelligence_analyst"),
    ):
        profile = AgentProfile(
            id=agent_id, name=name, department="intelligence-research",
            purpose="Complete assigned research", capabilities=("research",),
            state=AgentState.ACTIVE, role_key=role, team_key="intelligence-research__team_1",
        )
        store.save_agent_with_audit(profile, _event("agent.created", "agent_profile", agent_id))
    item = WorkItem(
        id=uuid4(), title="Research market", objective="Prepare a sourced report",
        department="intelligence-research", state=TaskState.IN_PROGRESS,
        assigned_agent_id=sender_id,
    )
    store.save_work_item_with_audit(item, _event("task.started", "work_item", item.id))
    now = datetime.now(timezone.utc)
    handoff = AgentHandoff(
        id=uuid4(), work_item_id=item.id, sender_agent_id=sender_id,
        recipient_agent_id=recipient_id, purpose="Competitor verification",
        requested_result="Verify the top three competitor claims",
        context="Review the evidence collected so far.",
        created_at=now, updated_at=now,
    )
    repository.create(handoff, _event("handoff.proposed", "agent_handoff", handoff.id))
    accepted = accept_handoff(handoff, at=datetime.now(timezone.utc))
    assert repository.transition(accepted, HandoffState.PROPOSED, _event("handoff.accepted", "agent_handoff", handoff.id))
    persisted = repository.get(handoff.id)
    assert persisted is not None and persisted.state == HandoffState.ACCEPTED
    assert repository.list_for_work_item(item.id) == (persisted,)
    assert store.verify_audit_chain()
    store.close()



def test_handoff_transition_cannot_rebind_to_another_business_work_item(tmp_path):
    store = SQLiteStore(tmp_path / "handoff-isolation.sqlite3")
    repository = HandoffRepository(store._connection, store._lock)
    sender_id, recipient_id = uuid4(), uuid4()
    for agent_id, name, role in (
        (sender_id, "Research Sender", "market_demand_researcher"),
        (recipient_id, "Research Recipient", "competitor_intelligence_analyst"),
    ):
        profile = AgentProfile(
            id=agent_id, name=name, department="intelligence-research",
            purpose="Complete assigned research", capabilities=("research",),
            state=AgentState.ACTIVE, role_key=role, team_key="intelligence-research__team_1",
        )
        store.save_agent_with_audit(profile, _event("agent.created", "agent_profile", agent_id))
    original = WorkItem(
        id=uuid4(), title="Agency research", objective="Prepare agency report",
        department="intelligence-research", state=TaskState.IN_PROGRESS,
        assigned_agent_id=sender_id, business_id="physical-agency",
    )
    other = WorkItem(
        id=uuid4(), title="Brand research", objective="Prepare brand report",
        department="intelligence-research", state=TaskState.IN_PROGRESS,
        assigned_agent_id=sender_id, business_id="physical-brand",
    )
    store.save_work_item_with_audit(original, _event("task.started", "work_item", original.id))
    store.save_work_item_with_audit(other, _event("task.started", "work_item", other.id))
    now = datetime.now(timezone.utc)
    handoff = AgentHandoff(
        id=uuid4(), work_item_id=original.id, sender_agent_id=sender_id,
        recipient_agent_id=recipient_id, purpose="Verify agency claims",
        requested_result="Verify the agency evidence",
        context="Only review the agency work item.",
        created_at=now, updated_at=now,
    )
    repository.create(handoff, _event("handoff.proposed", "agent_handoff", handoff.id))

    forged = replace(
        accept_handoff(handoff, at=datetime.now(timezone.utc)),
        work_item_id=other.id,
    )
    try:
        repository.transition(
            forged, HandoffState.PROPOSED,
            _event("handoff.accepted", "agent_handoff", handoff.id),
        )
        assert False, "cross-business handoff rebinding must be rejected"
    except ValueError as exc:
        assert "original identity or context" in str(exc)

    persisted = repository.get(handoff.id)
    assert persisted is not None
    assert persisted.work_item_id == original.id
    assert persisted.state == HandoffState.PROPOSED
    assert repository.list_for_work_item(other.id) == ()
    assert store.verify_audit_chain()
    store.close()
