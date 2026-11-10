import pytest

from opencompany_core.workforce import RoleCatalog, RoleSpec, default_workforce


def test_default_workforce_has_unique_original_roles():
    roles = default_workforce().all()
    assert len(roles) == 511
    assert len({role.key for role in roles}) == 511
    specialists = [role for role in roles if "__" in role.key]
    assert len(specialists) == 500
    assert all(role.function and role.mission and role.capabilities and role.permitted_outputs and role.prohibited_actions for role in specialists)
    assert all(role.playbook and len(role.playbook.workflow_steps) >= 5 for role in specialists)
    assert all(role.playbook.quality_rubric and role.playbook.escalation_triggers and role.playbook.tool_scopes for role in specialists)
    assert len({role.playbook.workflow_steps for role in specialists}) == 500
    assert len({role.team_key for role in specialists}) == 100
    assert all(sum(role.team_key == team for role in specialists) == 5 for team in {role.team_key for role in specialists})


def test_roles_define_scope_and_safety_boundaries():
    for role in default_workforce().all():
        assert role.mission
        assert role.capabilities
        assert role.permitted_outputs
        assert role.prohibited_actions
        assert role.playbook is not None
        assert len(role.playbook.intake_requirements) >= 3
        assert len(role.playbook.deliverable_contract) >= 3


def test_capability_matching_is_ranked_and_deterministic():
    catalog = default_workforce()
    matches = catalog.match(("market_research", "source_verification"))
    assert matches[0].key == "market_intelligence_analyst"


def test_empty_capability_request_returns_no_match():
    assert default_workforce().match(()) == ()


def test_unknown_role_fails_explicitly():
    with pytest.raises(LookupError, match="unknown OpenCompany role"):
        default_workforce().get("imported_specialist")


def test_duplicate_role_keys_are_rejected():
    role = RoleSpec("one", "Role", "Function", "Mission",
                    ("research",), ("brief",), ("external_action",))
    with pytest.raises(ValueError, match="unique"):
        RoleCatalog((role, role))


def test_role_with_no_safety_boundary_is_rejected():
    with pytest.raises(ValueError, match="prohibited actions"):
        RoleSpec("one", "Role", "Function", "Mission",
                 ("research",), ("brief",), ())
