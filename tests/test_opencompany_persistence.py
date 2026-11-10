from datetime import datetime, timezone
from uuid import uuid4

from opencompany_core.domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.persistence import SQLiteStore


def test_work_item_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    dependency = uuid4()
    item = WorkItem(uuid4(), "Prepare launch brief", "Produce a validated launch brief",
                    "product", state=TaskState.READY, depends_on=(dependency,))
    store.save_work_item(item)
    assert store.get_work_item(item.id) == item
    assert store.list_work_items(state=TaskState.READY) == (item,)
    store.close()


def test_agent_profile_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    agent = AgentProfile(uuid4(), "Market Analyst", "research",
                         "Assess market evidence", ("market_research",),
                         state=AgentState.ACTIVE)
    store.save_agent(agent)
    assert store.get_agent(agent.id) == agent
    store.close()


def audit_record(action):
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner",
        action=action, subject_type="work_item", subject_id="work-1",
        outcome="recorded", correlation_id="corr-1",
        details={"source": "unit-test"},
    )


def test_audit_chain_accepts_appended_events(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    store.append_audit_record(audit_record("work.created"))
    store.append_audit_record(audit_record("work.reviewed"))
    assert store.audit_event_count() == 2
    assert store.verify_audit_chain()
    store.close()


def test_audit_chain_detects_payload_tampering(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    store.append_audit_record(audit_record("work.created"))
    with store._lock:
        store._connection.execute(
            "UPDATE audit_events SET payload_json='{}' WHERE sequence=1"
        )
    assert not store.verify_audit_chain()
    store.close()


def test_invalid_list_limit_is_rejected(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    try:
        store.list_work_items(limit=0)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "limit" in str(exc)
    store.close()
