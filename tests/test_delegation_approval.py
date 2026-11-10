from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from opencompany_core.domain import AuditRecord, TaskState, WorkItem
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.persistence import SQLiteStore


def test_owner_approval_materializes_child_tasks_atomically(tmp_path):
    database = tmp_path / "shared.sqlite3"
    delegations = DelegationRepository(database)
    store = SQLiteStore(database)
    parent_id, agent_id = uuid4(), uuid4()
    child = {
        "assigned_agent_id": str(agent_id), "role_key": "research__source_analyst",
        "team_key": "intelligence-research__team_1", "title": "Source Analyst: Parent",
        "objective": "Prepare a reviewable evidence draft.",
    }
    proposal = delegations.create_proposal(
        parent_work_item_id=parent_id, request={"required_capabilities": ["source_verification"]},
        manager_agent_id=None, mode="specialist_team", team_key=child["team_key"],
        children=[child],
    )
    child_id = UUID(proposal["children"][0]["id"])
    task = WorkItem(
        id=child_id, title=child["title"], objective=child["objective"],
        department="Intelligence & Research", state=TaskState.READY,
        assigned_agent_id=agent_id,
    )
    now = datetime.now(timezone.utc)
    records = (
        AuditRecord(
            id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
            action="delegation.child_task_materialized", subject_type="work_item",
            subject_id=str(child_id), outcome="recorded", correlation_id=proposal["id"],
        ),
        AuditRecord(
            id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
            action="delegation.proposal_approved", subject_type="delegation_proposal",
            subject_id=proposal["id"], outcome="recorded", correlation_id=proposal["id"],
        ),
    )
    assert store.approve_delegation_proposal(UUID(proposal["id"]), (task,), records) is True
    saved = store.get_work_item(child_id)
    assert saved is not None and saved.state == TaskState.READY
    assert saved.assigned_agent_id == agent_id
    assert delegations.get_proposal(UUID(proposal["id"]))["status"] == "approved"
    assert store.verify_audit_chain() is True
    assert store.approve_delegation_proposal(UUID(proposal["id"]), (task,), records) is False
    assert store.list_work_items(limit=10) == (saved,)
    store.close()
    delegations.close()


def test_approval_rejects_mismatched_child_set_without_partial_write(tmp_path):
    database = tmp_path / "shared.sqlite3"
    delegations = DelegationRepository(database)
    store = SQLiteStore(database)
    parent_id = uuid4()
    child = {
        "assigned_agent_id": str(uuid4()), "role_key": "research__source_analyst",
        "team_key": "team_1", "title": "Draft", "objective": "Draft objective",
    }
    proposal = delegations.create_proposal(
        parent_work_item_id=parent_id, request={"required_capabilities": ["x"]},
        manager_agent_id=None, mode="specialist_team", team_key="team_1", children=[child],
    )
    unrelated = WorkItem(
        id=uuid4(), title="Unrelated", objective="No", department="Intelligence & Research",
        state=TaskState.READY,
    )
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="test", subject_type="work_item",
        subject_id=str(unrelated.id), outcome="recorded", correlation_id="test",
    )
    with pytest.raises(ValueError):
        store.approve_delegation_proposal(UUID(proposal["id"]), (unrelated,), (event,))
    assert store.get_work_item(unrelated.id) is None
    assert delegations.get_proposal(UUID(proposal["id"]))["status"] == "draft"
    assert store.audit_event_count() == 0
    store.close()
    delegations.close()
