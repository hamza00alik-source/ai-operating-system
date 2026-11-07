"""Provider-neutral storefront inventory and draft-only listing packets.

This module deliberately does not publish products, contact marketplaces, or
store credentials. Channels without a verified write API remain manual-export
channels until a dedicated adapter is implemented and tested.
"""
from __future__ import annotations

import os
import re

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/commerce", tags=["commerce"])

CHANNELS = {
    "woocommerce": {
        "label": "WooCommerce", "kind": "owned_store",
        "env": ("AI_OS_WOOCOMMERCE_URL", "AI_OS_WOOCOMMERCE_CONSUMER_KEY", "AI_OS_WOOCOMMERCE_CONSUMER_SECRET"),
        "integration": "existing_read_only_connector",
        "listing_mode": "owner_approved_unpublished_draft_only",
        "notes": "Reads catalog and minimized order status; separately gated product drafts only. No publishing, fulfillment, refunds, or payment writes.",
    },
    "gumroad": {
        "label": "Gumroad", "kind": "marketplace",
        "env": ("AI_OS_GUMROAD_ACCESS_TOKEN",),
        "integration": "manual_listing_packet", "listing_mode": "manual",
        "notes": "Official help documentation says product creation and content upload are not currently available through its API.",
    },
    "itch_io": {
        "label": "itch.io", "kind": "game_marketplace",
        "env": ("AI_OS_ITCH_API_KEY",),
        "integration": "read_api_plus_manual_listing", "listing_mode": "manual_or_owner_desktop_upload",
        "notes": "Server API documents account/game queries; uploads use butler tooling. No server-side product-create API is assumed.",
    },
    "cgtrader": {
        "label": "CGTrader", "kind": "3d_marketplace",
        "env": ("AI_OS_CGTRADER_TOKEN",),
        "integration": "manual_listing_packet", "listing_mode": "manual",
        "notes": "Seller onboarding, payout eligibility, and listing automation must be verified before a connector is built.",
    },
    "fab": {
        "label": "Fab", "kind": "3d_marketplace",
        "env": ("AI_OS_FAB_TOKEN",),
        "integration": "manual_listing_packet", "listing_mode": "manual",
        "notes": "Publisher onboarding, payout eligibility, and listing API permissions must be verified before a connector is built.",
    },
    "etsy": {
        "label": "Etsy", "kind": "marketplace",
        "env": ("AI_OS_ETSY_ACCESS_TOKEN",),
        "integration": "manual_listing_packet", "listing_mode": "manual",
        "notes": "Deferred until upfront listing and transaction costs are explicitly approved and unit economics are checked.",
    },
}

class ListingPacketRequest(BaseModel):
    channel: str
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(min_length=1, max_length=12000)
    product_type: str = Field(min_length=1, max_length=80)
    file_names: list[str] = Field(default_factory=list, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=20)
    price: str | None = Field(default=None, max_length=24)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("channel")
    @classmethod
    def known_channel(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in CHANNELS:
            raise ValueError("Unsupported storefront channel.")
        return value

    @field_validator("title", "description", "product_type")
    @classmethod
    def trim_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value

    @field_validator("file_names")
    @classmethod
    def safe_file_names(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            name = value.strip()
            if not name or len(name) > 180 or "/" in name or "\\" in name or name in {".", ".."}:
                raise ValueError("Use plain file names, not paths.")
            cleaned.append(name)
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("File names must be unique.")
        return cleaned

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values: list[str]) -> list[str]:
        cleaned = [tag.strip() for tag in values]
        if any(not tag or len(tag) > 30 for tag in cleaned):
            raise ValueError("Tags must contain 1 to 30 characters.")
        return list(dict.fromkeys(cleaned))

    @field_validator("price")
    @classmethod
    def valid_price(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,7})(?:\\.[0-9]{1,2})?", value):
            raise ValueError("Price must be a non-negative decimal with up to two places.")
        return value

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("Currency must be a three-letter code.")
        return value


def storefront_status() -> dict:
    rows = []
    for channel_id, spec in CHANNELS.items():
        configured = bool(spec["env"]) and all(os.getenv(key, "").strip() for key in spec["env"])
        rows.append({
            "id": channel_id, "name": spec["label"], "kind": spec["kind"],
            "configured": configured, "integration": spec["integration"],
            "listing_mode": spec["listing_mode"], "automated_publish": False,
            "status": "credentials_present_unverified" if configured else "not_connected",
            "notes": spec["notes"],
        })
    return {
        "mode": "draft_and_manual_export_only",
        "publishing_enabled": False, "external_actions_enabled": False,
        "storefronts": rows,
        "warning": "Credential presence does not prove account eligibility, API access, payout readiness, or live connectivity.",
    }


def build_listing_packet(request: ListingPacketRequest) -> dict:
    spec = CHANNELS[request.channel]
    return {
        "status": "draft_packet", "channel": request.channel,
        "channel_name": spec["label"],
        "product": {
            "title": request.title, "description": request.description,
            "product_type": request.product_type, "file_names": request.file_names,
            "tags": request.tags, "price": request.price, "currency": request.currency,
        },
        "channel_guidance": spec["notes"],
        "approval_required_before_upload_or_publish": True,
        "upload_performed": False, "published": False,
    }


@router.get("/storefronts")
def get_storefront_status():
    """Owner-authenticated status inventory; does not make outbound requests."""
    return storefront_status()


@router.post("/listing-packets", status_code=201)
def create_listing_packet(request: ListingPacketRequest):
    """Create a local listing draft only; never contacts or publishes to a channel."""
    return build_listing_packet(request)
