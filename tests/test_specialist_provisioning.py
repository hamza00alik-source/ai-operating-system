from opencompany_core.domain import AgentState
from opencompany_core.persistence import SQLiteStore
from opencompany_core.provisioning import bootstrap_specialist_profiles


def test_bootstrap_creates_500_draft_specialists_idempotently(tmp_path):
    store = SQLiteStore(tmp_path / "specialists.sqlite3")
    first = bootstrap_specialist_profiles(store)
    second = bootstrap_specialist_profiles(store)
    assert len(first) == 500
    assert len(second) == 500
    assert len({item.id for item in first}) == 500
    assert all(item.state == AgentState.DRAFT for item in first)
    assert all(item.role_key and item.team_key for item in first)
    departments = {}
    for item in first:
        departments[item.department] = departments.get(item.department, 0) + 1
    assert len(departments) == 10
    assert set(departments.values()) == {50}
    assert store.audit_event_count() == 500
    assert store.verify_audit_chain()
    assert len(store.list_agents(limit=1000)) == 500
    assert store.activate_all_draft_agents_with_audit() == 500
    activated = store.list_agents(limit=1000)
    assert all(item.state == AgentState.ACTIVE and item.revision == 2 for item in activated)
    assert store.audit_event_count() == 1000
    assert store.verify_audit_chain()
    store.close()
