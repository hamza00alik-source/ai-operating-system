import pytest

from opencompany_core.persistence import SQLiteStore
from opencompany_core.venture_portfolio import VenturePortfolio
from opencompany_core.business_units import BusinessUnitRegistry, BusinessUnitProvisioningError


def setup():
    store = SQLiteStore(":memory:")
    portfolio = VenturePortfolio(store._connection, store._lock)
    registry = BusinessUnitRegistry(store._connection, store._lock)
    return store, portfolio, registry


def approved_opportunity(portfolio):
    item = portfolio.create(
        title="Research subscription",
        slug="research-subscription",
        business_model="subscription-software",
        description="A research product with recurring access.",
        target_market="International small businesses",
    )
    portfolio.transition(item["id"], status="researching", rationale="Collect evidence")
    return portfolio.transition(
        item["id"], status="validated", rationale="Evidence supports a test"
    ) and portfolio.transition(
        item["id"], status="approved_to_launch",
        rationale="Owner approves launch planning", confirm_owner_approval=True,
    )


def provision(registry, portfolio, item, **overrides):
    values = {
        "business_id": "research-subscription-co",
        "name": "Research Subscription Co",
        "unit_type": "software",
        "delivery_class": "software-access",
        "description": "Subscription research access only; no unrelated fulfilment.",
        "target_market": "International small businesses",
        "confirm_owner_approval": True,
    }
    values.update(overrides)
    return registry.provision_from_opportunity(portfolio, item["id"], **values)


def test_foundational_businesses_are_registered_with_separate_delivery_classes():
    store, _, registry = setup()
    try:
        units = {item["business_id"]: item for item in registry.list()}
        assert units["physical-agency"]["delivery_class"] == "physical-goods"
        assert units["physical-brand"]["delivery_class"] == "physical-goods"
        assert units["digital-products"]["delivery_class"] == "digital-files"
        assert units["physical-agency"]["customer_scope_id"] != units["physical-brand"]["customer_scope_id"]
    finally:
        store.close()


def test_provisioning_requires_approved_opportunity_and_owner_confirmation():
    store, portfolio, registry = setup()
    try:
        item = portfolio.create(
            title="New service", slug="new-service", business_model="services",
            description="A defined service offer", target_market="SMBs",
        )
        with pytest.raises(BusinessUnitProvisioningError, match="approved for launch planning"):
            provision(registry, portfolio, item)
        approved = approved_opportunity(portfolio)
        with pytest.raises(BusinessUnitProvisioningError, match="explicit owner approval"):
            provision(registry, portfolio, approved, confirm_owner_approval=False)
    finally:
        store.close()


def test_provisioning_creates_distinct_scopes_but_does_not_activate_unit():
    store, portfolio, registry = setup()
    try:
        item = approved_opportunity(portfolio)
        unit = provision(registry, portfolio, item)
        assert unit["status"] == "provisioning"
        assert unit["source_opportunity_id"] == item["id"]
        scopes = [
            unit["namespace_id"], unit["customer_scope_id"], unit["finance_scope_id"],
            unit["credential_scope_id"], unit["integration_scope_id"],
            unit["memory_scope_id"], unit["asset_scope_id"],
        ]
        assert len(scopes) == len(set(scopes)) == 7
        assert portfolio.get(item["id"])["status"] == "approved_to_launch"
        assert registry.events(unit["business_id"])[0]["action"] == "provisioned"
    finally:
        store.close()


def test_business_delivery_class_is_strict_and_ids_are_unique():
    store, portfolio, registry = setup()
    try:
        item = approved_opportunity(portfolio)
        with pytest.raises(BusinessUnitProvisioningError, match="cross-type fulfilment"):
            provision(
                registry, portfolio, item,
                business_id="bad-digital-business",
                unit_type="digital-products", delivery_class="physical-goods",
            )
        provision(registry, portfolio, item)
        with pytest.raises(BusinessUnitProvisioningError, match="already exists"):
            provision(registry, portfolio, item)
    finally:
        store.close()
