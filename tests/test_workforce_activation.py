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


def test_api_rejects_unknown_team_before_activation():
    import pytest
    from fastapi import HTTPException
    from opencompany_app.api import WorkforceActivationInput, activate_workforce_scope

    class Store:
        def list_agents(self, *, limit):
            return []

        def activate_all_draft_agents_with_audit(self, **kwargs):
            raise AssertionError("invalid team must be rejected before activation")

    with pytest.raises(HTTPException) as error:
        activate_workforce_scope(
            WorkforceActivationInput(
                department="intelligence-research",
                team_key="not-a-registered-team",
            ),
            Store(),
        )
    assert error.value.status_code == 422


def test_api_activates_only_the_requested_department_scope():
    from opencompany_app.api import WorkforceActivationInput, activate_workforce_scope

    class Store:
        def __init__(self):
            self.activation_scope = None

        def list_agents(self, *, limit):
            return []

        def activate_all_draft_agents_with_audit(self, **kwargs):
            self.activation_scope = kwargs
            return 7

    store = Store()
    result = activate_workforce_scope(
        WorkforceActivationInput(department="intelligence-research"),
        store,
    )

    assert result["activated_count"] == 7
    assert result["worker_execution_started"] is False
    assert store.activation_scope == {
        "department": "intelligence-research",
        "team_key": None,
    }


def test_api_rejects_profile_with_inconsistent_role_team_identity():
    import pytest
    from fastapi import HTTPException
    from opencompany_app.api import WorkforceActivationInput, activate_workforce_scope

    malformed = _profile(
        department="intelligence-research",
        team_key="wrong-team",
        role_key="market_intelligence_analyst",
    )

    class Store:
        def list_agents(self, *, limit):
            return [malformed]

        def activate_all_draft_agents_with_audit(self, **kwargs):
            raise AssertionError("inconsistent profile must not be activated")

    with pytest.raises(HTTPException) as error:
        activate_workforce_scope(
            WorkforceActivationInput(department="intelligence-research"),
            Store(),
        )
    assert error.value.status_code == 409


def test_api_rejects_profile_role_from_another_department():
    import pytest
    from fastapi import HTTPException
    from opencompany_app.api import WorkforceActivationInput, activate_workforce_scope

    malformed = _profile(
        department="intelligence-research",
        team_key="management",
        role_key="product_planning_lead",
    )

    class Store:
        def list_agents(self, *, limit):
            return [malformed]

        def activate_all_draft_agents_with_audit(self, **kwargs):
            raise AssertionError("cross-department role must not be activated")

    with pytest.raises(HTTPException) as error:
        activate_workforce_scope(
            WorkforceActivationInput(department="intelligence-research"),
            Store(),
        )
    assert error.value.status_code == 409
