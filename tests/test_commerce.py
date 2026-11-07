import pytest
from pydantic import ValidationError

from ai_os.commerce import CHANNELS, ListingPacketRequest, build_listing_packet, storefront_status


def test_all_requested_storefronts_are_registered():
    assert {"woocommerce", "gumroad", "itch_io", "cgtrader", "fab", "etsy"} <= set(CHANNELS)


def test_storefront_status_is_safe_and_does_not_claim_live_connection(monkeypatch):
    for spec in CHANNELS.values():
        for key in spec["env"]:
            monkeypatch.delenv(key, raising=False)
    result = storefront_status()
    assert result["publishing_enabled"] is False
    assert result["external_actions_enabled"] is False
    assert all(row["status"] == "not_connected" for row in result["storefronts"])
    assert all(row["automated_publish"] is False for row in result["storefronts"])


def test_configured_only_means_credentials_present_not_verified(monkeypatch):
    monkeypatch.setenv("AI_OS_GUMROAD_ACCESS_TOKEN", "placeholder-not-a-real-token")
    row = next(row for row in storefront_status()["storefronts"] if row["id"] == "gumroad")
    assert row["configured"] is True
    assert row["status"] == "credentials_present_unverified"
    assert row["automated_publish"] is False


def test_listing_packet_is_draft_only_and_contains_no_side_effect():
    request = ListingPacketRequest(
        channel="itch_io", title="Original Sci-Fi UI Pack",
        description="A downloadable UI pack.", product_type="game_ui_assets",
        file_names=["preview.png", "assets.zip"], tags=["sci-fi", "ui"],
        price="2.99", currency="USD",
    )
    packet = build_listing_packet(request)
    assert packet["status"] == "draft_packet"
    assert packet["published"] is False
    assert packet["upload_performed"] is False
    assert packet["approval_required_before_upload_or_publish"] is True
    assert packet["product"]["price"] == "2.99"


@pytest.mark.parametrize("channel", ["gumroad", "itch_io", "cgtrader", "fab", "etsy"])
def test_marketplace_channels_validate(channel):
    request = ListingPacketRequest(
        channel=channel, title="Pack", description="Description",
        product_type="digital_asset",
    )
    assert request.channel == channel


def test_unknown_channel_rejected():
    with pytest.raises(ValidationError):
        ListingPacketRequest(channel="unknown", title="Pack", description="Description", product_type="digital_asset")


@pytest.mark.parametrize("filename", ["../secret.txt", "folder/file.zip", "folder\\\\file.zip", ".."])
def test_listing_packet_rejects_paths(filename):
    with pytest.raises(ValidationError):
        ListingPacketRequest(
            channel="gumroad", title="Pack", description="Description",
            product_type="digital_asset", file_names=[filename],
        )


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity", "1.234", "1e5", "01.00"])
def test_invalid_prices_rejected(price):
    with pytest.raises(ValidationError):
        ListingPacketRequest(
            channel="gumroad", title="Pack", description="Description",
            product_type="digital_asset", price=price,
        )


def test_duplicate_file_names_rejected():
    with pytest.raises(ValidationError):
        ListingPacketRequest(
            channel="gumroad", title="Pack", description="Description",
            product_type="digital_asset", file_names=["pack.zip", "pack.zip"],
        )
