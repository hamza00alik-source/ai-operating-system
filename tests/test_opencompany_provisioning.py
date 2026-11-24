from opencompany_core.domain import AgentState
from opencompany_core.persistence import SQLiteStore
from opencompany_core.provisioning import bootstrap_department_managers


def test_bootstrap_creates_ten_draft_manager_profiles_and_is_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "organization.sqlite3")
    first = bootstrap_department_managers(store)
    second = bootstrap_department_managers(store)
    assert len(first) == 10
    assert len(second) == 10
    assert len({item.id for item in first}) == 10
    assert all(item.state == AgentState.DRAFT for item in first)
    assert all(item.role_key and item.team_key == "management" for item in first)
    assert {item.department for item in first} == {
        "executive-office", "intelligence-research", "product-innovation",
        "engineering-ai-systems", "media-creative-production",
        "marketing-audience-growth", "revenue-partnerships",
        "customer-operations", "finance-risk", "organizational-learning-quality",
    }
    assert store.audit_event_count() == 10
    assert store.verify_audit_chain()
    store.close()
