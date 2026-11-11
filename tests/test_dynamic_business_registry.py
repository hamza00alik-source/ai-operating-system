import ai_os.business_registry as registry
from ai_os.team_architecture import business_scope_context


def test_custom_registered_business_gets_its_own_agent_contract(monkeypatch):
    monkeypatch.setattr(registry, "BUSINESS_IDS", set(registry.BUILTIN_BUSINESSES) | {"subscription-service"})
    monkeypatch.setattr(
        registry,
        "get_business",
        lambda business_id: {
            "id": "subscription-service",
            "name": "Subscription Service",
            "business_type": "services",
            "description": "Recurring remote bookkeeping service for small companies.",
            "status": "active",
        },
    )
    context = business_scope_context("subscription-service")
    assert "Subscription Service" in context
    assert "Recurring remote bookkeeping service" in context
    assert "customers, finances, credentials" in context
    assert "owner approval" in context


def test_custom_physical_venture_inherits_physical_fulfillment_boundary(monkeypatch):
    import pytest
    import ai_os.business_scope as scope

    monkeypatch.setattr(scope, "require_business", lambda business_id: business_id)
    monkeypatch.setattr(scope, "get_business", lambda business_id: {"business_type": "physical-products"})
    with pytest.raises(ValueError, match="cannot fulfil an order"):
        scope.validate_business_task_scope(
            "specialty-foods",
            "Ship downloadable software to fulfil the customer's physical goods order",
        )


def test_custom_digital_venture_inherits_digital_fulfillment_boundary(monkeypatch):
    import pytest
    import ai_os.business_scope as scope

    monkeypatch.setattr(scope, "require_business", lambda business_id: business_id)
    monkeypatch.setattr(scope, "get_business", lambda business_id: {"business_type": "digital-products"})
    with pytest.raises(ValueError, match="cannot promise or fulfil"):
        scope.validate_business_task_scope(
            "subscription-software",
            "Ship physical goods to the customer as part of their order",
        )
