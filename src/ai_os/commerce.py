"""Provider-neutral storefront inventory and draft-only listing packets.

This module deliberately does not publish products, contact marketplaces, or
store credentials. Channels without a verified write API remain manual-export
channels until a dedicated adapter is implemented and tested.
"""
from __future__ import annotations

import os
import re
import base64

from fastapi import APIRouter, Query
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
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,7})(?:[.][0-9]{1,2})?", value):
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


# Local canonical catalog, idempotent order ledger, and fulfillment review queue.
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Header, HTTPException, Request
from ai_os.db import connect
from ai_os.audit import append_event


def initialize_commerce_storage() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS commerce_products (
            id TEXT PRIMARY KEY,
            sku TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            product_type TEXT NOT NULL,
            files_json TEXT NOT NULL DEFAULT '[]',
            tags_json TEXT NOT NULL DEFAULT '[]',
            base_price TEXT,
            currency TEXT,
            status TEXT NOT NULL CHECK(status IN ('draft','approved','archived')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS commerce_listings (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            packet_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','approved_for_manual_upload','listed','paused')),
            external_listing_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(product_id, channel),
            FOREIGN KEY(product_id) REFERENCES commerce_products(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS commerce_orders (
            id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            external_order_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            currency TEXT NOT NULL,
            total TEXT NOT NULL,
            items_json TEXT NOT NULL,
            received_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(channel, external_order_id)
        );
        CREATE TABLE IF NOT EXISTS commerce_fulfillment (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('awaiting_review','ready_after_payment_check','fulfilled_manually','blocked')),
            delivery_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES commerce_orders(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS commerce_entitlements (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            external_item_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('awaiting_manual_delivery','delivered_manually','revoked')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(order_id, product_id),
            FOREIGN KEY(order_id) REFERENCES commerce_orders(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES commerce_products(id)
        );
        CREATE INDEX IF NOT EXISTS idx_commerce_orders_channel_status
            ON commerce_orders(channel, status, received_at DESC);
        """)


class CatalogProductCreate(BaseModel):
    sku: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(min_length=1, max_length=12000)
    product_type: str = Field(min_length=1, max_length=80)
    file_names: list[str] = Field(default_factory=list, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=20)
    base_price: str | None = Field(default=None, max_length=24)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(row):
    return dict(row) if row else None


@router.post("/catalog/products", status_code=201)
def create_catalog_product(payload: CatalogProductCreate, request: Request):
    # Canonical records are saved as drafts. No marketplace or store is contacted.
    packet = ListingPacketRequest(
        channel="woocommerce", title=payload.title, description=payload.description,
        product_type=payload.product_type, file_names=payload.file_names,
        tags=payload.tags, price=payload.base_price, currency=payload.currency,
    )
    now, product_id = _now(), str(uuid4())
    with connect() as db:
        try:
            db.execute(
                """INSERT INTO commerce_products
                (id,sku,title,description,product_type,files_json,tags_json,base_price,currency,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'draft',?,?)""",
                (product_id, payload.sku, packet.title, packet.description, packet.product_type,
                 json.dumps(packet.file_names), json.dumps(packet.tags), packet.price,
                 packet.currency, now, now),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="SKU already exists.") from exc
            raise
    append_event(getattr(request.state, "actor", "unknown"), "commerce_product_drafted",
                 "commerce_product", product_id, {"sku": payload.sku})
    return {"id": product_id, "sku": payload.sku, "title": payload.title, "status": "draft"}


@router.get("/catalog/products")
def list_catalog_products(limit: int = Query(default=100, ge=1, le=500)):
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM commerce_products ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"products": [
        {**dict(row), "files": json.loads(row["files_json"]), "tags": json.loads(row["tags_json"])}
        for row in rows
    ]}


@router.post("/catalog/products/{product_id}/listing-packets", status_code=201)
def create_product_listing_packet(product_id: str, channel: str, request: Request):
    with connect() as db:
        product = db.execute("SELECT * FROM commerce_products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found.")
        if channel not in CHANNELS:
            raise HTTPException(status_code=422, detail="Unsupported storefront channel.")
        payload = ListingPacketRequest(
            channel=channel, title=product["title"], description=product["description"],
            product_type=product["product_type"], file_names=json.loads(product["files_json"]),
            tags=json.loads(product["tags_json"]), price=product["base_price"],
            currency=product["currency"],
        )
        packet = build_listing_packet(payload)
        now, listing_id = _now(), str(uuid4())
        try:
            db.execute(
                """INSERT INTO commerce_listings
                (id,product_id,channel,packet_json,status,created_at,updated_at)
                VALUES (?,?,?,?, 'draft',?,?)""",
                (listing_id, product_id, channel, json.dumps(packet), now, now),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="A listing packet already exists for this product and channel.") from exc
            raise
    append_event(getattr(request.state, "actor", "unknown"), "commerce_listing_packet_created",
                 "commerce_listing", listing_id, {"product_id": product_id, "channel": channel})
    return {"id": listing_id, **packet}


@router.post("/listings/{listing_id}/approve-manual-upload")
def approve_manual_listing_packet(listing_id: str, request: Request):
    actor = getattr(request.state, "actor", "unknown")
    if actor != "owner":
        raise HTTPException(status_code=403, detail="A configured owner token is required.")
    now = _now()
    with connect() as db:
        row = db.execute("SELECT status,channel FROM commerce_listings WHERE id=?", (listing_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Listing packet not found.")
        if row["status"] != "draft":
            raise HTTPException(status_code=409, detail="Only draft listing packets can be approved.")
        db.execute(
            "UPDATE commerce_listings SET status='approved_for_manual_upload',updated_at=? WHERE id=?",
            (now, listing_id),
        )
    append_event(actor, "commerce_listing_packet_approved_for_manual_upload",
                 "commerce_listing", listing_id, {"channel": row["channel"]})
    return {"id": listing_id, "status": "approved_for_manual_upload",
            "external_upload_performed": False, "published": False}


@router.post("/listings/{listing_id}/map-external-id")
def map_external_listing_id(listing_id: str, external_listing_id: str, request: Request):
    actor = getattr(request.state, "actor", "unknown")
    if actor != "owner":
        raise HTTPException(status_code=403, detail="A configured owner token is required.")
    external_listing_id = external_listing_id.strip()
    if not external_listing_id or len(external_listing_id) > 120:
        raise HTTPException(status_code=422, detail="A valid external listing ID is required.")
    now = _now()
    with connect() as db:
        row = db.execute("SELECT channel,status FROM commerce_listings WHERE id=?", (listing_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Listing packet not found.")
        if row["status"] not in {"approved_for_manual_upload", "listed"}:
            raise HTTPException(status_code=409, detail="Approve the manual listing packet before mapping its marketplace ID.")
        db.execute(
            "UPDATE commerce_listings SET external_listing_id=?,status='listed',updated_at=? WHERE id=?",
            (external_listing_id, now, listing_id),
        )
    append_event(actor, "commerce_external_listing_mapped", "commerce_listing", listing_id,
                 {"channel": row["channel"], "external_listing_id": external_listing_id})
    return {"id": listing_id, "channel": row["channel"], "status": "listed",
            "external_listing_id": external_listing_id, "marketplace_contacted": False}


@router.get("/listings")
def list_commerce_listings(limit: int = Query(default=100, ge=1, le=500)):
    with connect() as db:
        rows = db.execute(
            """SELECT l.*, p.sku, p.title AS product_title
            FROM commerce_listings l JOIN commerce_products p ON p.id=l.product_id
            ORDER BY l.created_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    return {"listings": [
        {**dict(row), "packet": json.loads(row["packet_json"])} for row in rows
    ]}


def _normalize_order(channel: str, raw: dict) -> dict:
    external_id = str(raw.get("id", "")).strip()
    if not external_id or len(external_id) > 120:
        raise HTTPException(status_code=422, detail="Order ID is required.")
    status = str(raw.get("status", "unknown"))[:40]
    payment = "paid" if raw.get("date_paid") else "not_confirmed"
    currency = str(raw.get("currency", "USD")).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "XXX"
    total = str(raw.get("total", "0"))
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,9})(?:[.][0-9]{1,2})?", total):
        total = "0"
    items = []
    for item in raw.get("line_items", [])[:100]:
        if not isinstance(item, dict):
            continue
        items.append({
            "product_id": str(item.get("product_id", ""))[:80],
            "name": str(item.get("name", ""))[:180],
            "quantity": max(0, min(int(item.get("quantity", 0) or 0), 10000)),
            "total": str(item.get("total", "0"))[:24],
        })
    return {"external_order_id": external_id, "status": status, "payment_status": payment,
            "currency": currency, "total": total, "items": items}


def ingest_order(channel: str, raw: dict) -> dict:
    normalized = _normalize_order(channel, raw)
    now = _now()
    with connect() as db:
        existing = db.execute(
            "SELECT id FROM commerce_orders WHERE channel=? AND external_order_id=?",
            (channel, normalized["external_order_id"]),
        ).fetchone()
        if existing:
            order_id = existing["id"]
            db.execute(
                """UPDATE commerce_orders SET status=?,payment_status=?,currency=?,total=?,items_json=?,updated_at=?
                WHERE id=?""",
                (normalized["status"], normalized["payment_status"], normalized["currency"],
                 normalized["total"], json.dumps(normalized["items"]), now, order_id),
            )
            created = False
        else:
            order_id = str(uuid4())
            db.execute(
                """INSERT INTO commerce_orders
                (id,channel,external_order_id,status,payment_status,currency,total,items_json,received_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (order_id, channel, normalized["external_order_id"], normalized["status"],
                 normalized["payment_status"], normalized["currency"], normalized["total"],
                 json.dumps(normalized["items"]), now, now),
            )
            fulfillment_status = "ready_after_payment_check" if normalized["payment_status"] == "paid" else "awaiting_review"
            db.execute(
                """INSERT INTO commerce_fulfillment
                (id,order_id,status,created_at,updated_at) VALUES (?,?,?,?,?)""",
                (str(uuid4()), order_id, fulfillment_status, now, now),
            )
            created = True
        if normalized["payment_status"] == "paid":
            # Match marketplace item IDs to owner-recorded listing mappings.
            for item in normalized["items"]:
                if not item["product_id"]:
                    continue
                mapped = db.execute(
                    """SELECT l.product_id FROM commerce_listings l
                    WHERE l.channel=? AND l.external_listing_id=? AND l.status='listed'""",
                    (channel, item["product_id"]),
                ).fetchone()
                if mapped:
                    db.execute(
                        """INSERT OR IGNORE INTO commerce_entitlements
                        (id,order_id,product_id,channel,external_item_id,status,created_at,updated_at)
                        VALUES (?,?,?,?,?,'awaiting_manual_delivery',?,?)""",
                        (str(uuid4()), order_id, mapped["product_id"], channel,
                         item["product_id"], now, now),
                    )
        fulfillment = db.execute(
            "SELECT status FROM commerce_fulfillment WHERE order_id=?", (order_id,)
        ).fetchone()
    return {"id": order_id, "channel": channel, "external_order_id": normalized["external_order_id"],
            "payment_status": normalized["payment_status"], "created": created,
            "fulfillment_status": fulfillment["status"] if fulfillment else "missing"}


@router.post("/webhooks/woocommerce", status_code=202)
async def receive_woocommerce_order_webhook(request: Request, x_wc_webhook_signature: str = Header(default="")):
    secret = os.getenv("AI_OS_WOOCOMMERCE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="WooCommerce webhook secret is not configured.")
    body = await request.body()
    expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    if not x_wc_webhook_signature or not hmac.compare_digest(expected, x_wc_webhook_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")
    try:
        payload = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Expected an order object.")
    result = ingest_order("woocommerce", payload)
    append_event("woocommerce_webhook", "commerce_order_ingested", "commerce_order",
                 result["id"], {"external_order_id": result["external_order_id"],
                                "payment_status": result["payment_status"], "created": result["created"]})
    return result


@router.get("/orders")
def list_commerce_orders(limit: int = Query(default=100, ge=1, le=500)):
    with connect() as db:
        rows = db.execute(
            """SELECT o.*, f.status AS fulfillment_status
            FROM commerce_orders o LEFT JOIN commerce_fulfillment f ON f.order_id=o.id
            ORDER BY o.received_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    return {"orders": [
        {**dict(row), "items": json.loads(row["items_json"])} for row in rows
    ]}


@router.get("/entitlements")
def list_commerce_entitlements(limit: int = Query(default=100, ge=1, le=500)):
    with connect() as db:
        rows = db.execute(
            """SELECT e.*, p.sku, p.title AS product_title
            FROM commerce_entitlements e JOIN commerce_products p ON p.id=e.product_id
            ORDER BY e.created_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    return {"entitlements": [dict(row) for row in rows],
            "policy": "Entitlements are internal records only; no download URL or customer notification is generated."}


@router.get("/fulfillment")
def list_fulfillment_queue(limit: int = Query(default=100, ge=1, le=500)):
    with connect() as db:
        rows = db.execute(
            """SELECT f.*, o.channel, o.external_order_id, o.payment_status, o.status AS order_status
            FROM commerce_fulfillment f JOIN commerce_orders o ON o.id=f.order_id
            ORDER BY f.created_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    return {"fulfillment": [dict(row) for row in rows],
            "policy": "No delivery is performed automatically. Verify payment and product entitlement before manual fulfillment."}


@router.get("/overview")
def commerce_overview():
    with connect() as db:
        products = db.execute("SELECT status,COUNT(*) AS count FROM commerce_products GROUP BY status").fetchall()
        listings = db.execute("SELECT status,COUNT(*) AS count FROM commerce_listings GROUP BY status").fetchall()
        orders = db.execute("SELECT channel,payment_status,COUNT(*) AS count FROM commerce_orders GROUP BY channel,payment_status").fetchall()
        fulfillment = db.execute("SELECT status,COUNT(*) AS count FROM commerce_fulfillment GROUP BY status").fetchall()
    return {
        "storefronts": storefront_status()["storefronts"],
        "products": {row["status"]: row["count"] for row in products},
        "listings": {row["status"]: row["count"] for row in listings},
        "orders": [dict(row) for row in orders],
        "fulfillment": {row["status"]: row["count"] for row in fulfillment},
        "payout_reconciliation": "not_connected_no_payout_data",
        "automated_fulfillment": False,
    }
