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
                         state=AgentState.ACTIVE, role_key="market_intelligence_analyst",
                         team_key="management")
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


def test_work_item_and_audit_record_commit_together(tmp_path):
    store = SQLiteStore(tmp_path / "opencompany.sqlite3")
    item = WorkItem(uuid4(), "Review product brief", "Verify product requirements",
                    "quality", state=TaskState.REVIEW)
    event = audit_record("work_item.review")
    store.save_work_item_with_audit(item, event)
    assert store.get_work_item(item.id) == item
    assert store.audit_event_count() == 1
    assert store.verify_audit_chain()
    store.close()


def test_schema_v1_migrates_agent_role_identity_columns(tmp_path):
    import sqlite3

    path = tmp_path / "legacy-v1.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE agent_profiles (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, department TEXT NOT NULL,
            purpose TEXT NOT NULL, capabilities_json TEXT NOT NULL,
            state TEXT NOT NULL, revision INTEGER NOT NULL
        );
        CREATE TABLE work_items (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, objective TEXT NOT NULL,
            department TEXT NOT NULL, state TEXT NOT NULL, assigned_agent_id TEXT,
            dependencies_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE audit_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE
        );
        PRAGMA user_version = 1;
    """)
    connection.close()

    store = SQLiteStore(path)
    columns = {row["name"] for row in store._connection.execute(
        "PRAGMA table_info(agent_profiles)"
    ).fetchall()}
    version = store._connection.execute("PRAGMA user_version").fetchone()[0]
    assert {"role_key", "team_key"} <= columns
    assert version == 2
    store.close()
