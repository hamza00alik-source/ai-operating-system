import pytest

from opencompany_core.workforce import RoleCatalog, RoleSpec, default_workforce


def test_default_workforce_has_unique_original_roles():
    roles = default_workforce().all()
    assert len(roles) == 261
    assert len({role.key for role in roles}) == 261
    specialists = [role for role in roles if "__" in role.key]
    assert len(specialists) == 250
    assert all(role.function and role.mission and role.capabilities and role.permitted_outputs and role.prohibited_actions for role in specialists)


def test_roles_define_scope_and_safety_boundaries():
    for role in default_workforce().all():
        assert role.mission
        assert role.capabilities
        assert role.permitted_outputs
        assert role.prohibited_actions


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
