import base64
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.commerce import initialize_commerce_storage, ingest_order
from ai_os.db import connect


def test_order_ingestion_is_idempotent_and_requires_payment_timestamp(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'commerce.sqlite'}")
    initialize_commerce_storage()
    pending = {
        "id": 123, "status": "processing", "currency": "USD", "total": "4.99",
        "date_paid": None,
        "line_items": [{"product_id": 9, "name": "UI pack", "quantity": 1, "total": "4.99"}],
        "billing": {"email": "must-not-be-stored@example.com"},
    }
    first = ingest_order("woocommerce", pending)
    second = ingest_order("woocommerce", pending)
    assert first["created"] is True
    assert second["created"] is False
    assert first["id"] == second["id"]
    with connect() as db:
        order = db.execute("SELECT * FROM commerce_orders WHERE id=?", (first["id"],)).fetchone()
        fulfillment = db.execute("SELECT * FROM commerce_fulfillment WHERE order_id=?", (first["id"],)).fetchone()
    assert order["payment_status"] == "not_confirmed"
    assert "must-not-be-stored" not in str(dict(order))
    assert fulfillment["status"] == "awaiting_review"


def test_paid_order_moves_only_to_review_ready_not_auto_fulfilled(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'commerce-paid.sqlite'}")
    initialize_commerce_storage()
    order = {
        "id": 456, "status": "processing", "currency": "USD", "total": "2.00",
        "date_paid": "2026-11-07T10:00:00",
        "line_items": [{"product_id": 2, "name": "Icon pack", "quantity": 1, "total": "2.00"}],
    }
    result = ingest_order("woocommerce", order)
    assert result["payment_status"] == "paid"
    with connect() as db:
        fulfillment = db.execute("SELECT status FROM commerce_fulfillment WHERE order_id=?", (result["id"],)).fetchone()
    assert fulfillment["status"] == "ready_after_payment_check"


def test_woocommerce_webhook_hmac_and_idempotent_order_ingestion(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'commerce-hook.sqlite'}")
    monkeypatch.setenv("AI_OS_WOOCOMMERCE_WEBHOOK_SECRET", "test-webhook-secret")
    body = json.dumps({
        "id": 789, "status": "completed", "currency": "USD", "total": "7.50",
        "date_paid": "2026-11-07T10:00:00",
        "line_items": [{"product_id": 5, "name": "Asset", "quantity": 1, "total": "7.50"}],
    }).encode()
    signature = base64.b64encode(
        hmac.new(b"test-webhook-secret", body, hashlib.sha256).digest()
    ).decode()
    with TestClient(app) as client:
        denied = client.post("/commerce/webhooks/woocommerce", content=body)
        first = client.post(
            "/commerce/webhooks/woocommerce", content=body,
            headers={"X-WC-Webhook-Signature": signature},
        )
        second = client.post(
            "/commerce/webhooks/woocommerce", content=body,
            headers={"X-WC-Webhook-Signature": signature},
        )
    assert denied.status_code == 401
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["created"] is True
    assert second.json()["created"] is False


def test_catalog_product_and_channel_listing_packet_are_local_drafts(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'commerce-catalog.sqlite'}")
    with TestClient(app) as client:
        created = client.post("/commerce/catalog/products", json={
            "sku": "SCI-FI-UI-001", "title": "Sci-Fi UI Pack",
            "description": "Original downloadable interface assets.",
            "product_type": "game_ui_assets", "file_names": ["assets.zip"],
            "tags": ["sci-fi", "ui"], "base_price": "2.99", "currency": "USD",
        })
        assert created.status_code == 201
        product_id = created.json()["id"]
        listing = client.post(f"/commerce/catalog/products/{product_id}/listing-packets?channel=itch_io")
        overview = client.get("/commerce/overview")
    assert listing.status_code == 201
    assert listing.json()["published"] is False
    assert listing.json()["upload_performed"] is False
    assert overview.status_code == 200
    assert overview.json()["automated_fulfillment"] is False


def test_manual_listing_approval_requires_owner_and_never_publishes(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'commerce-approval.sqlite'}")
    owner_key = "x" * 64
    monkeypatch.setenv("AI_OS_API_TOKEN", owner_key)
    with TestClient(app) as client:
        product = client.post("/commerce/catalog/products", json={
            "sku": "APPROVAL-001", "title": "Asset", "description": "Digital file",
            "product_type": "asset", "file_names": ["asset.zip"],
        }, headers={"Authorization": "Bearer " + owner_key})
        listing = client.post(
            f"/commerce/catalog/products/{product.json()['id']}/listing-packets?channel=gumroad",
            headers={"Authorization": "Bearer " + owner_key},
        )
        listing_id = listing.json()["id"]
        denied = client.post(f"/commerce/listings/{listing_id}/approve-manual-upload")
        approved = client.post(
            f"/commerce/listings/{listing_id}/approve-manual-upload",
            headers={"Authorization": "Bearer " + owner_key},
        )
    assert product.status_code == 201
    assert listing.status_code == 201
    assert denied.status_code == 401
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved_for_manual_upload"
    assert approved.json()["external_upload_performed"] is False
    assert approved.json()["published"] is False
