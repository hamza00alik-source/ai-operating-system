"""Owner-authenticated, read-only storefront registry endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.storefronts import DEFAULT_STOREFRONT_REGISTRY
from opencompany_app.api_dependencies import require_owner_key


router = APIRouter()


@router.get("/storefronts/channels", dependencies=[Depends(require_owner_key)])
def list_storefront_channels(business_id: str | None = None) -> dict:
    try:
        channels = DEFAULT_STOREFRONT_REGISTRY.list_channels(business_id=business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "count": len(channels),
        "channels": [DEFAULT_STOREFRONT_REGISTRY.public_record(item) for item in channels],
        "mode": "read_only_registry",
        "external_writes_enabled": False,
    }


@router.get("/storefronts/channels/{channel_id}", dependencies=[Depends(require_owner_key)])
def get_storefront_channel(channel_id: str) -> dict:
    try:
        channel = DEFAULT_STOREFRONT_REGISTRY.get_channel(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Storefront channel not found.") from exc
    return {
        "channel": DEFAULT_STOREFRONT_REGISTRY.public_record(channel),
        "mode": "read_only_registry",
        "external_writes_enabled": False,
    }
