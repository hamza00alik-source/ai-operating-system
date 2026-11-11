from uuid import uuid4

from opencompany_core.domain import AgentProfile, AgentState
from opencompany_core.persistence import SQLiteStore


def _profile(*, department: str, team_key: str, role_key: str) -> AgentProfile:
    return AgentProfile(
        id=uuid4(),
        name=role_key.replace("_", " ").title(),
        department=department,
        purpose="Prepare internal draft work",
        capabilities=("internal_draft",),
        state=AgentState.DRAFT,
        role_key=role_key,
        team_key=team_key,
    )


def test_scoped_activation_only_activates_selected_team_and_is_audited(tmp_path):
    store = SQLiteStore(tmp_path / "activation.sqlite3")
    selected = _profile(
        department="intelligence-research",
        team_key="intelligence_research__team_1",
        role_key="intelligence_research__market_analyst",
    )
    other_team = _profile(
        department="intelligence-research",
        team_key="intelligence_research__team_2",
        role_key="intelligence_research__competitor_analyst",
    )
    other_department = _profile(
        department="product-innovation",
        team_key="product_innovation__team_1",
        role_key="product_innovation__product_analyst",
    )
    for profile in (selected, other_team, other_department):
        store.save_agent(profile)

    activated = store.activate_all_draft_agents_with_audit(
        department="intelligence-research",
        team_key="intelligence_research__team_1",
    )

    assert activated == 1
    assert store.get_agent(selected.id).state == AgentState.ACTIVE
    assert store.get_agent(other_team.id).state == AgentState.DRAFT
    assert store.get_agent(other_department.id).state == AgentState.DRAFT
    assert store.verify_audit_chain()
    store.close()


def test_department_activation_preserves_other_departments(tmp_path):
    store = SQLiteStore(tmp_path / "department-activation.sqlite3")
    research = _profile(
        department="intelligence-research",
        team_key="management",
        role_key="market_intelligence_analyst",
    )
    product = _profile(
        department="product-innovation",
        team_key="management",
        role_key="product_planning_lead",
    )
    store.save_agent(research)
    store.save_agent(product)

    activated = store.activate_all_draft_agents_with_audit(
        department="intelligence-research",
    )

    assert activated == 1
    assert store.get_agent(research.id).state == AgentState.ACTIVE
    assert store.get_agent(product.id).state == AgentState.DRAFT
    assert store.verify_audit_chain()
    store.close()


def test_team_activation_requires_department(tmp_path):
    store = SQLiteStore(tmp_path / "invalid-scope.sqlite3")
    try:
        import pytest

        with pytest.raises(ValueError, match="requires a department"):
            store.activate_all_draft_agents_with_audit(team_key="team_1")
    finally:
        store.close()
