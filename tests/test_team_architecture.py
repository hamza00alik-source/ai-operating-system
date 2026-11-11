import pytest

from ai_os.team_architecture import business_scope_context, team_contract_context


@pytest.mark.parametrize(
    ("business_id", "required", "forbidden"),
    [
        ("physical-agency", "third-party physical-product", "digital download"),
        ("physical-brand", "own physical-product brand", "digital product"),
        ("digital-products", "downloadable digital products", "physical goods"),
    ],
)
def test_business_scope_contract_is_explicit_and_separate(business_id, required, forbidden):
    context = business_scope_context(business_id)
    assert required.casefold() in context.casefold()
    assert forbidden.casefold() in context.casefold()
    assert "single business environment" in context


def test_unknown_business_scope_fails_closed():
    with pytest.raises(ValueError, match="Unknown business environment"):
        business_scope_context("some-other-business")


def test_core_scope_is_internal_only():
    context = business_scope_context("core")
    assert "Internal OpenCompany platform" in context
    assert "customer order" in context


def test_team_contract_defines_distinct_roles_and_shared_context_boundaries():
    contract = team_contract_context()
    assert "lead specialist" in contract
    assert "independent collaborator" in contract
    assert "CEO" in contract
    assert "cross-business information" in contract
