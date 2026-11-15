"""Persistent, business-scoped private storefront listing drafts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .domain import AuditRecord
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json


class StorefrontPersistenceMixin:
    """Store private listing packets; this mixin has no platform network access."""

    def create_storefront_listing_draft(
        self, draft: dict[str, Any], audit: AuditRecord
    ) -> dict[str, Any]:
        allowed = {"physical-agency", "physical-brand", "digital-products"}
        business_id = draft.get("business_id")
        if business_id not in allowed:
            raise ValueError("listing drafts must belong to one commercial business unit")
        if not all(isinstance(draft.get(key), str) and draft[key].strip()
                   for key in ("id", "canonical_product_id", "channel_id", "title")):
            raise ValueError("listing draft identity, product, channel and title are required")
        now = datetime.now(timezone.utc).isoformat()
        payload = dict(draft)
        payload.update({
            "status": "draft",
            "visibility": "private",
            "owner_approval_required_before_publish": True,
            "external_write_performed": False,
        })
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                product = self._connection.execute(
                    "SELECT business_id FROM commercial_products WHERE id=?",
                    (draft["canonical_product_id"],),
                ).fetchone()
                if product is None:
                    raise ValueError("canonical product does not exist")
                if product["business_id"] != business_id:
                    raise ValueError("listing draft business unit must match its canonical product")
                self._connection.execute(
                    """INSERT INTO storefront_listing_drafts
                       (id,canonical_product_id,business_id,channel_id,title,payload_json,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,'draft',?,?)""",
                    (draft["id"], draft["canonical_product_id"], business_id,
                     draft["channel_id"], draft["title"], _json(payload), now, now),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                audit_payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(audit_payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(audit_payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
        return {"id": draft["id"], **payload, "created_at": now, "updated_at": now}

    def get_storefront_listing_draft(self, listing_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM storefront_listing_drafts WHERE id=?", (listing_id,)
            ).fetchone()
        if row is None:
            return None
        import json
        return {**json.loads(row["payload_json"]), "id": row["id"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_storefront_listing_drafts(
        self, *, business_id: str | None = None, channel_id: str | None = None,
        limit: int = 200,
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if business_id is not None and business_id not in {
            "physical-agency", "physical-brand", "digital-products"
        }:
            raise ValueError("unknown commercial business unit")
        clauses, values = [], []
        if business_id is not None:
            clauses.append("business_id=?")
            values.append(business_id)
        if channel_id is not None:
            clauses.append("channel_id=?")
            values.append(channel_id)
        sql = "SELECT * FROM storefront_listing_drafts"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC,id LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(sql, tuple(values)).fetchall()
        import json
        return tuple({
            **json.loads(row["payload_json"]), "id": row["id"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        } for row in rows)
