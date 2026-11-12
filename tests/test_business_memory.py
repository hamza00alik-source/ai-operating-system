from datetime import datetime, timezone
from uuid import uuid4
import pytest
from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_core.business_memory import BusinessMemoryStore


def audit(action="business.memory_saved", actor_type="owner"):
    return AuditRecord(id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type=actor_type, actor_id="owner" if actor_type=="owner" else "agent-1",
        action=action, subject_type="business_memory", subject_id="test",
        outcome="stored", correlation_id=str(uuid4()), details={})


def test_business_memory_isolated_versioned_and_tombstoned(tmp_path):
    store=SQLiteStore(tmp_path/"memory.sqlite3")
    memory=BusinessMemoryStore(store._connection,store._lock)
    first=memory.put("physical-agency","buyer-profile","strategy","International wholesale buyers","owner note",audit())
    assert first["revision"]==1
    assert memory.list("physical-brand")==()
    second=memory.put("physical-agency","buyer-profile","strategy","Verified buyer segment","owner note",audit())
    assert second["revision"]==2
    assert memory.get("physical-agency","buyer-profile")["content"]=="Verified buyer segment"
    assert len(memory.history("physical-agency","buyer-profile"))==2
    removed=memory.forget("physical-agency","buyer-profile",audit("business.memory_forgotten"))
    assert removed["operation"]=="tombstone"
    assert memory.get("physical-agency","buyer-profile") is None
    assert memory.history("physical-agency","buyer-profile")[0]["operation"]=="tombstone"
    store.close()


def test_business_memory_rejects_secret_markers_and_agent_writes(tmp_path):
    store=SQLiteStore(tmp_path/"memory.sqlite3")
    memory=BusinessMemoryStore(store._connection,store._lock)
    with pytest.raises(ValueError):
        memory.put("physical-agency","secret","operations","api_key=abc","owner note",audit())
    with pytest.raises(PermissionError):
        memory.put("physical-agency","agent-note","operations","agent memory","agent source",audit(actor_type="agent"))
    store.close()


def test_memory_versions_are_database_append_only(tmp_path):
    store=SQLiteStore(tmp_path/"memory.sqlite3")
    memory=BusinessMemoryStore(store._connection,store._lock)
    memory.put("physical-agency","policy","operations","Owner approved policy","owner note",audit())
    with pytest.raises(Exception):
        store._connection.execute("DELETE FROM opencompany_business_memory_versions")
    store.close()
