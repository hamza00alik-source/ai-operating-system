"""Provider-neutral storefront contracts and a fail-closed channel registry.

This module deliberately contains no network client, credential handling, or
external write operation. Platform capabilities remain unverified until they
are supported by official documentation and an owner-authorized account check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence


_CHANNEL_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_BUSINESS_UNITS = frozenset({"physical-agency", "physical-brand", "digital-products"})
_CAPABILITIES = (
    "product_read", "listing_create", "listing_update", "order_ingestion",
    "digital_delivery", "refunds", "customer_messaging", "payout_reporting",
    "country_payout_eligibility",
)


@dataclass(frozen=True, slots=True)
class StorefrontChannel:
    """A channel's intended role; not proof of platform/API capability."""

    id: str
    name: str
    purpose: str
    business_units: tuple[str, ...]
    product_types: tuple[str, ...]
    priority: str = "later"
    connection_state: str = "not_connected"
    verification_state: str = "unverified"
    external_write_enabled: bool = False

    def __post_init__(self) -> None:
        if not _CHANNEL_ID.fullmatch(self.id):
            raise ValueError("channel id must be a lowercase slug")
        if not self.name.strip() or not self.purpose.strip():
            raise ValueError("channel name and purpose are required")
        if not self.business_units or any(item not in _BUSINESS_UNITS for item in self.business_units):
            raise ValueError("channel must reference known commercial business units")
        if len(set(self.business_units)) != len(self.business_units):
            raise ValueError("business unit assignments must be unique")
        if self.connection_state not in {"not_connected", "connected_read_only", "write_enabled"}:
            raise ValueError("unsupported connection state")
        if self.verification_state not in {"unverified", "partially_verified", "verified"}:
            raise ValueError("unsupported verification state")
        if self.external_write_enabled:
            raise ValueError("external writes are disabled in the storefront foundation")
        if self.connection_state == "write_enabled":
            raise ValueError("write-enabled channels are not supported in this release")


class StorefrontRegistry:
    """Registry with no credentials or external actions."""

    def __init__(self, channels: Sequence[StorefrontChannel]) -> None:
        indexed: dict[str, StorefrontChannel] = {}
        for channel in channels:
            if channel.id in indexed:
                raise ValueError(f"duplicate storefront channel: {channel.id}")
            indexed[channel.id] = channel
        self._channels = indexed

    def list_channels(self, *, business_id: str | None = None) -> tuple[StorefrontChannel, ...]:
        if business_id is not None and business_id not in _BUSINESS_UNITS:
            raise ValueError("unknown commercial business unit")
        channels = (
            channel for channel in self._channels.values()
            if business_id is None or business_id in channel.business_units
        )
        return tuple(sorted(channels, key=lambda item: (item.priority != "primary", item.name.casefold())))

    def get_channel(self, channel_id: str) -> StorefrontChannel:
        try:
            return self._channels[channel_id]
        except KeyError as exc:
            raise KeyError(f"unknown storefront channel: {channel_id}") from exc

    @staticmethod
    def public_record(channel: StorefrontChannel) -> dict:
        return {
            "id": channel.id,
            "name": channel.name,
            "purpose": channel.purpose,
            "business_units": list(channel.business_units),
            "product_types": list(channel.product_types),
            "priority": channel.priority,
            "connection_state": channel.connection_state,
            "verification_state": channel.verification_state,
            "capabilities": {key: "unverified" for key in _CAPABILITIES},
            "external_write_enabled": False,
            "listing_drafts_supported_internally": True,
        }


DEFAULT_STOREFRONT_REGISTRY = StorefrontRegistry((
    StorefrontChannel(
        id="woocommerce", name="WooCommerce",
        purpose="Primary owned storefront for the company's own catalogue.",
        business_units=("physical-brand", "digital-products"),
        product_types=("physical-goods", "digital-files"), priority="primary",
    ),
    StorefrontChannel(
        id="gumroad", name="Gumroad",
        purpose="Candidate channel for downloadable digital products.",
        business_units=("digital-products",), product_types=("digital-files",),
    ),
    StorefrontChannel(
        id="itch-io", name="itch.io",
        purpose="Candidate channel for game-related downloadable products.",
        business_units=("digital-products",), product_types=("game-assets", "digital-files"),
    ),
    StorefrontChannel(
        id="cgtrader", name="CGTrader",
        purpose="Candidate channel for downloadable 3D models and assets.",
        business_units=("digital-products",), product_types=("3d-models",),
    ),
    StorefrontChannel(
        id="etsy", name="Etsy",
        purpose="Later-stage candidate for digital product discovery.",
        business_units=("digital-products",), product_types=("digital-files",),
    ),
    StorefrontChannel(
        id="fab", name="Fab",
        purpose="Later-stage candidate for game-ready digital assets.",
        business_units=("digital-products",), product_types=("game-assets", "3d-models"),
    ),
    StorefrontChannel(
        id="unity-asset-store", name="Unity Asset Store",
        purpose="Later-stage candidate for Unity-compatible digital assets.",
        business_units=("digital-products",), product_types=("game-assets",),
    ),
))


@dataclass(frozen=True, slots=True)
class ListingDraft:
    """Internal listing packet. Constructing it never contacts a platform."""

    canonical_product_id: str
    business_id: str
    channel_id: str
    title: str
    description: str
    tags: tuple[str, ...] = ()
    price_amount: Decimal | None = None
    currency: str | None = None
    license_text: str | None = None
    media_refs: tuple[str, ...] = ()
    package_ref: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("canonical_product_id", "channel_id", "title", "description"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        if self.business_id not in _BUSINESS_UNITS:
            raise ValueError("listing draft must belong to a commercial business unit")
        if not _CHANNEL_ID.fullmatch(self.channel_id):
            raise ValueError("channel_id must be a lowercase slug")
        if (self.price_amount is None) != (self.currency is None):
            raise ValueError("price amount and currency must be supplied together")
        if self.price_amount is not None:
            amount = Decimal(self.price_amount)
            if not amount.is_finite() or amount < 0:
                raise ValueError("listing price must be finite and non-negative")
            if not self.currency or not re.fullmatch(r"[A-Z]{3}", self.currency):
                raise ValueError("currency must be a three-letter uppercase code")
        if any(not tag.strip() for tag in self.tags):
            raise ValueError("listing tags cannot be empty")
        if any(not ref.strip() for ref in self.media_refs):
            raise ValueError("media references cannot be empty")

    def to_public_record(self) -> dict:
        return {
            "canonical_product_id": self.canonical_product_id,
            "business_id": self.business_id,
            "channel_id": self.channel_id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "price_amount": str(self.price_amount) if self.price_amount is not None else None,
            "currency": self.currency,
            "license_text": self.license_text,
            "media_refs": list(self.media_refs),
            "package_ref": self.package_ref,
            "status": "draft",
            "visibility": "private",
            "owner_approval_required_before_publish": True,
            "external_write_performed": False,
        }


class StorefrontAdapter(Protocol):
    """Contract for future channel adapters; implementations must be least-privilege."""

    channel_id: str

    def prepare_listing_draft(self, product: dict) -> ListingDraft:
        """Prepare a local draft only; must not publish or update a remote listing."""
        ...
