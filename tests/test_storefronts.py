from decimal import Decimal

import pytest

from opencompany_core.storefronts import (
    DEFAULT_STOREFRONT_REGISTRY,
    ListingDraft,
    StorefrontChannel,
    StorefrontRegistry,
)


def test_default_registry_contains_initial_and_later_channels():
    channels = DEFAULT_STOREFRONT_REGISTRY.list_channels()
    assert {item.id for item in channels} == {
        "woocommerce", "gumroad", "itch-io", "cgtrader", "etsy", "fab", "unity-asset-store"
    }
    assert channels[0].id == "woocommerce"


def test_all_external_capabilities_are_unverified_and_writes_disabled():
    for channel in DEFAULT_STOREFRONT_REGISTRY.list_channels():
        public = DEFAULT_STOREFRONT_REGISTRY.public_record(channel)
        assert channel.connection_state == "not_connected"
        assert channel.verification_state == "unverified"
        assert channel.external_write_enabled is False
        assert public["external_write_enabled"] is False
        assert set(public["capabilities"].values()) == {"unverified"}


def test_registry_filters_by_business_unit_without_crossing_scopes():
    ids = {item.id for item in DEFAULT_STOREFRONT_REGISTRY.list_channels(business_id="digital-products")}
    assert ids == {"woocommerce", "gumroad", "itch-io", "cgtrader", "etsy", "fab", "unity-asset-store"}
    assert {item.id for item in DEFAULT_STOREFRONT_REGISTRY.list_channels(business_id="physical-brand")} == {"woocommerce"}


def test_registry_rejects_unknown_business_and_duplicate_channels():
    with pytest.raises(ValueError, match="unknown commercial business unit"):
        DEFAULT_STOREFRONT_REGISTRY.list_channels(business_id="unknown")
    channel = StorefrontChannel("example-store", "Example", "Test", ("digital-products",), ("digital-files",))
    with pytest.raises(ValueError, match="duplicate storefront channel"):
        StorefrontRegistry((channel, channel))


def test_unknown_channel_is_not_silently_resolved():
    with pytest.raises(KeyError, match="unknown storefront channel"):
        DEFAULT_STOREFRONT_REGISTRY.get_channel("not-a-store")


def test_listing_draft_is_private_and_never_performs_external_write():
    draft = ListingDraft(
        canonical_product_id="product-123",
        business_id="digital-products",
        channel_id="itch-io",
        title="Original Game Asset Pack",
        description="A downloadable game asset pack.",
        tags=("game-assets", "original"),
        price_amount=Decimal("0"),
        currency="USD",
        license_text="Draft license; owner approval required.",
        media_refs=("artifact://preview.png",),
        package_ref="artifact://product.zip",
    )
    public = draft.to_public_record()
    assert public["status"] == "draft"
    assert public["visibility"] == "private"
    assert public["owner_approval_required_before_publish"] is True
    assert public["external_write_performed"] is False
    assert public["price_amount"] == "0"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"business_id": "core"},
        {"channel_id": "Bad Channel"},
        {"price_amount": Decimal("-1"), "currency": "USD"},
        {"price_amount": Decimal("1"), "currency": "usd"},
        {"price_amount": Decimal("1")},
    ],
)
def test_listing_draft_rejects_invalid_scope_and_price(kwargs):
    values = {
        "canonical_product_id": "product-123",
        "business_id": "digital-products",
        "channel_id": "itch-io",
        "title": "Asset",
        "description": "Description",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        ListingDraft(**values)
