from opencompany_core.domain import AgentState
from opencompany_core.persistence import SQLiteStore
from opencompany_core.provisioning import bootstrap_specialist_profiles


def test_bootstrap_creates_250_draft_specialists_idempotently(tmp_path):
    store = SQLiteStore(tmp_path / "specialists.sqlite3")
    first = bootstrap_specialist_profiles(store)
    second = bootstrap_specialist_profiles(store)
    assert len(first) == 250
    assert len(second) == 250
    assert len({item.id for item in first}) == 250
    assert all(item.state == AgentState.DRAFT for item in first)
    assert all(item.role_key and item.team_key for item in first)
    departments = {}
    for item in first:
        departments[item.department] = departments.get(item.department, 0) + 1
    assert len(departments) == 10
    assert set(departments.values()) == {25}
    assert store.audit_event_count() == 250
    assert store.verify_audit_chain()
    assert len(store.list_agents(limit=1000)) == 250
    store.close()
