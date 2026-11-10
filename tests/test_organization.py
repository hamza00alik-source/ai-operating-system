from dataclasses import replace
import pytest
from opencompany_core.organization import OrganizationCatalog, default_organization


def test_original_organization_has_ten_unique_departments():
    departments = default_organization().all()
    assert len(departments) == 10
    assert len({item.key for item in departments}) == 10


def test_every_department_manager_and_member_is_a_known_opencompany_role():
    from opencompany_core.workforce import default_workforce
    roles = default_workforce()
    for department in default_organization().all():
        roles.get(department.manager_role_key)
        for role_key in department.role_keys:
            roles.get(role_key)
        specialists = [key for key in department.role_keys if "__" in key]
        assert len(specialists) == 50
    assert sum(len([key for key in item.role_keys if "__" in key]) for item in default_organization().all()) == 500


def test_department_contracts_include_accountability_metrics_and_approval_boundaries():
    for department in default_organization().all():
        assert department.mission
        assert department.accountabilities
        assert department.decision_scope
        assert department.success_measures
        assert department.approval_boundaries


def test_duplicate_department_keys_are_rejected():
    department = default_organization().all()[0]
    with pytest.raises(ValueError, match="unique"):
        OrganizationCatalog((department, department))


def test_unknown_role_assignment_is_rejected():
    department = replace(default_organization().all()[0], role_keys=("not-a-role",),
                         manager_role_key="not-a-role")
    with pytest.raises(LookupError, match="unknown OpenCompany role"):
        OrganizationCatalog((department,))
