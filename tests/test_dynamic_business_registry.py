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
