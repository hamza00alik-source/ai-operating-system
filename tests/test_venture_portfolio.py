from opencompany_core.persistence import SQLiteStore
from opencompany_core.venture_portfolio import VenturePortfolio, VenturePortfolioError


def portfolio():
    store = SQLiteStore(":memory:")
    return store, VenturePortfolio(store._connection, store._lock)


def test_portfolio_accepts_new_business_models_without_changing_operating_units():
    store, registry = portfolio()
    try:
        item = registry.create(
            title="Niche research subscription",
            slug="niche-research-subscription",
            business_model="subscription-software",
            description="A research product for a defined professional audience.",
            target_market="International small businesses",
            evidence=[{"url": "https://example.com/pricing", "note": "Public pricing page"}],
        )
        assert item["business_model"] == "subscription-software"
        assert item["status"] == "discovered"
        assert item["evidence"][0]["url"] == "https://example.com/pricing"
    finally:
        store.close()


def test_launch_approval_is_explicit_and_separate_from_discovery():
    store, registry = portfolio()
    try:
        item = registry.create(
            title="Digital template studio",
            slug="digital-template-studio",
            business_model="digital-downloads",
            description="Create and sell downloadable templates.",
            target_market="Global creators",
        )
        item = registry.transition(item["id"], status="researching", rationale="Collect demand evidence")
        item = registry.transition(item["id"], status="validated", rationale="Evidence supports a test")
        try:
            registry.transition(item["id"], status="approved_to_launch", rationale="Ready")
            assert False, "launch approval must not be implicit"
        except VenturePortfolioError:
            pass
        item = registry.transition(
            item["id"], status="approved_to_launch", rationale="Owner approved a limited launch",
            confirm_owner_approval=True,
        )
        assert item["status"] == "approved_to_launch"
        item = registry.transition(
            item["id"], status="launched", rationale="Owner confirmed launch completion",
            confirm_owner_approval=True,
        )
        assert item["status"] == "launched"
        assert len(registry.events(item["id"])) == 5
    finally:
        store.close()


def test_evidence_requires_https_and_invalid_transitions_are_rejected():
    store, registry = portfolio()
    try:
        try:
            registry.create(
                title="Bad evidence sample", slug="bad-evidence-sample",
                business_model="services", description="Test", target_market="Global",
                evidence=[{"url": "http://example.com"}],
            )
            assert False, "non-HTTPS evidence must be rejected"
        except VenturePortfolioError:
            pass
        item = registry.create(
            title="Consulting offer", slug="consulting-offer",
            business_model="services", description="A scoped service offer",
            target_market="SMBs",
        )
        try:
            registry.transition(item["id"], status="launched", rationale="skip stages", confirm_owner_approval=True)
            assert False, "invalid lifecycle transitions must be rejected"
        except VenturePortfolioError:
            pass
    finally:
        store.close()
