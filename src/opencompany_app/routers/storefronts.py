"""Owner-authenticated, read-only storefront registry endpoints."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_app.api_schemas import StorefrontListingDraftInput
from opencompany_app.api_dependencies import get_store

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



@router.post("/storefronts/listing-drafts", dependencies=[Depends(require_owner_key)])
def create_storefront_listing_draft(
    payload: StorefrontListingDraftInput,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    try:
        channel = DEFAULT_STOREFRONT_REGISTRY.get_channel(payload.channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Storefront channel not found.") from exc
    if payload.business_id not in channel.business_units:
        raise HTTPException(status_code=422, detail="Storefront channel is not assigned to this business unit.")
    if (payload.price_amount is None) != (payload.currency is None):
        raise HTTPException(status_code=422, detail="Price amount and currency must be supplied together.")
    try:
        amount = Decimal(payload.price_amount) if payload.price_amount is not None else None
        draft = ListingDraft(
            canonical_product_id=str(payload.canonical_product_id),
            business_id=payload.business_id,
            channel_id=payload.channel_id,
            title=payload.title.strip(),
            description=payload.description.strip(),
            tags=tuple(item.strip() for item in payload.tags),
            price_amount=amount,
            currency=payload.currency,
            license_text=payload.license_text,
            media_refs=tuple(item.strip() for item in payload.media_refs),
            package_ref=payload.package_ref,
        )
        listing_id = str(uuid4())
        record = {"id": listing_id, **draft.to_public_record()}
        result = store.create_storefront_listing_draft(record, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner",
            action="storefront.listing_draft_created",
            subject_type="storefront_listing_draft", subject_id=listing_id,
            outcome="draft", correlation_id=str(uuid4()),
            details={"business_id": payload.business_id, "channel_id": payload.channel_id,
                     "external_write_performed": False},
        ))
    except (ValueError, InvalidOperation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/storefronts/listing-drafts", dependencies=[Depends(require_owner_key)])
def list_storefront_listing_drafts(
    business_id: str | None = None,
    channel_id: str | None = None,
    limit: int = 200,
    store: SQLiteStore = Depends(get_store),
) -> dict:
    try:
        records = store.list_storefront_listing_drafts(
            business_id=business_id, channel_id=channel_id, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(records), "listing_drafts": records,
            "external_writes_enabled": False}


@router.get("/storefronts/listing-drafts/{listing_id}", dependencies=[Depends(require_owner_key)])
def get_storefront_listing_draft(
    listing_id: UUID, store: SQLiteStore = Depends(get_store)
) -> dict:
    record = store.get_storefront_listing_draft(str(listing_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Listing draft not found.")
    return {"listing_draft": record, "external_writes_enabled": False}
