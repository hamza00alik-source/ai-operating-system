from datetime import datetime, timezone
from uuid import uuid4

import pytest

from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore


def _audit(action: str, subject_id: str) -> AuditRecord:
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type="storefront_listing_draft", subject_id=subject_id,
        outcome="draft", correlation_id=str(uuid4()),
        details={"external_write_performed": False},
    )


def _product(store: SQLiteStore, business_id: str = "digital-products") -> str:
    product_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    store.create_commercial_product({
        "id": product_id, "business_id": business_id,
        "name": "Original game asset", "description": "Test product",
        "category": "game-assets", "status": "draft",
        "created_at": now, "updated_at": now,
    }, _audit("commercial.product_created", product_id))
    return product_id


def test_storefront_listing_draft_persists_privately_and_is_audited(tmp_path):
    store = SQLiteStore(tmp_path / "storefront.sqlite3")
    product_id = _product(store)
    listing_id = str(uuid4())
    result = store.create_storefront_listing_draft({
        "id": listing_id, "canonical_product_id": product_id,
        "business_id": "digital-products", "channel_id": "itch-io",
        "title": "Original game asset pack", "description": "Downloadable files",
        "tags": ["game-assets"], "price_amount": "0", "currency": "USD",
        "media_refs": [], "package_ref": None,
    }, _audit("storefront.listing_draft_created", listing_id))
    assert result["status"] == "draft"
    assert result["visibility"] == "private"
    assert result["owner_approval_required_before_publish"] is True
    assert result["external_write_performed"] is False
    assert store.get_storefront_listing_draft(listing_id)["title"] == "Original game asset pack"
    assert store.list_storefront_listing_drafts(business_id="digital-products")[0]["id"] == listing_id
    assert store.audit_event_count() == 2
    assert store.verify_audit_chain()
    store.close()


def test_storefront_listing_draft_rejects_product_business_unit_mismatch(tmp_path):
    store = SQLiteStore(tmp_path / "storefront-scope.sqlite3")
    product_id = _product(store, "physical-brand")
    listing_id = str(uuid4())
    with pytest.raises(ValueError, match="must match"):
        store.create_storefront_listing_draft({
            "id": listing_id, "canonical_product_id": product_id,
            "business_id": "digital-products", "channel_id": "itch-io",
            "title": "Wrong business",
        }, _audit("storefront.listing_draft_created", listing_id))
    assert store.get_storefront_listing_draft(listing_id) is None
    assert store.audit_event_count() == 1
    store.close()


def test_storefront_listing_draft_requires_existing_product(tmp_path):
    store = SQLiteStore(tmp_path / "storefront-missing-product.sqlite3")
    listing_id = str(uuid4())
    with pytest.raises(ValueError, match="does not exist"):
        store.create_storefront_listing_draft({
            "id": listing_id, "canonical_product_id": str(uuid4()),
            "business_id": "digital-products", "channel_id": "itch-io",
            "title": "Orphan",
        }, _audit("storefront.listing_draft_created", listing_id))
    assert store.audit_event_count() == 0
    store.close()


def test_storefront_listing_draft_list_is_scoped_and_bounded(tmp_path):
    store = SQLiteStore(tmp_path / "storefront-list.sqlite3")
    product_id = _product(store)
    for channel in ("itch-io", "cgtrader"):
        listing_id = str(uuid4())
        store.create_storefront_listing_draft({
            "id": listing_id, "canonical_product_id": product_id,
            "business_id": "digital-products", "channel_id": channel,
            "title": channel,
        }, _audit("storefront.listing_draft_created", listing_id))
    assert len(store.list_storefront_listing_drafts(channel_id="itch-io")) == 1
    assert len(store.list_storefront_listing_drafts(business_id="digital-products")) == 2
    with pytest.raises(ValueError, match="limit"):
        store.list_storefront_listing_drafts(limit=0)
    store.close()
