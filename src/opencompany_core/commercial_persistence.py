"""Commercial-domain SQLite repository operations mixed into SQLiteStore."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .domain import AuditRecord
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json


class CommercialPersistenceMixin:
    """Commercial records share the store's connection, lock and audit transaction."""

    def create_commercial_opportunity(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Create one customer opportunity scoped to exactly one commercial business."""
        allowed = {"physical-agency", "physical-brand", "digital-products"}
        if record.get("business_id") not in allowed:
            raise ValueError("opportunities must belong to one commercial business unit")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO commercial_opportunities
                       (id,business_id,customer_name,customer_contact,customer_need,stage,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (record["id"], record["business_id"], record["customer_name"],
                     record.get("customer_contact"), record["customer_need"],
                     record.get("stage", "new"), record["created_at"], record["updated_at"]),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(payload), previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def get_commercial_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM commercial_opportunities WHERE id=?", (opportunity_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_commercial_opportunities(
        self, *, business_id: str | None = None, limit: int = 500
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if business_id is not None and business_id not in {
            "physical-agency", "physical-brand", "digital-products"
        }:
            raise ValueError("unknown commercial business unit")
        sql = "SELECT * FROM commercial_opportunities"
        values: list[Any] = []
        if business_id is not None:
            sql += " WHERE business_id=?"
            values.append(business_id)
        sql += " ORDER BY created_at DESC,id LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(sql, tuple(values)).fetchall()
        return tuple(dict(row) for row in rows)

    def create_commercial_quote(
        self, record: dict[str, Any], items: list[dict[str, Any]], audit: AuditRecord
    ) -> dict[str, Any]:
        """Create a draft quote; every line must use an active product in the opportunity's unit."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                opportunity = self._connection.execute(
                    "SELECT * FROM commercial_opportunities WHERE id=?",
                    (record["opportunity_id"],),
                ).fetchone()
                if opportunity is None:
                    raise ValueError("commercial opportunity not found")
                business_id = opportunity["business_id"]
                if business_id != record["business_id"]:
                    raise ValueError("quote business must match its opportunity")
                if opportunity["stage"] in {"lost", "on_hold"}:
                    raise ValueError("a lost or on-hold opportunity cannot receive a new quote")
                if record["currency_exponent"] not in {0, 2, 3}:
                    raise ValueError("currency exponent must be 0, 2, or 3")
                if not items:
                    raise ValueError("a quote must contain at least one line item")
                subtotal = 0
                for item in items:
                    product = self._connection.execute(
                        "SELECT business_id,status FROM commercial_products WHERE id=?",
                        (item["product_id"],),
                    ).fetchone()
                    if product is None or product["status"] != "active":
                        raise ValueError("quote items must reference active catalogue entries")
                    if product["business_id"] != business_id:
                        raise ValueError("cross-business quote lines are prohibited")
                    line_total = item["quantity"] * item["unit_price_minor"]
                    if line_total > 9_000_000_000_000_000:
                        raise ValueError("quote line total exceeds the supported amount")
                    subtotal += line_total
                    if subtotal > 9_000_000_000_000_000:
                        raise ValueError("quote subtotal exceeds the supported amount")
                if subtotal != record["subtotal_minor"]:
                    raise ValueError("quote subtotal does not match its line items")
                self._connection.execute(
                    """INSERT INTO commercial_quotes
                       (id,opportunity_id,business_id,title,currency,currency_exponent,subtotal_minor,terms,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,'draft',?,?)""",
                    (record["id"], record["opportunity_id"], business_id, record["title"],
                     record["currency"], record["currency_exponent"], subtotal, record["terms"], record["created_at"], record["updated_at"]),
                )
                for item in items:
                    self._connection.execute(
                        """INSERT INTO commercial_quote_items
                           (id,quote_id,product_id,description,quantity,unit_price_minor,line_total_minor)
                           VALUES(?,?,?,?,?,?,?)""",
                        (item["id"], record["id"], item["product_id"], item["description"],
                         item["quantity"], item["unit_price_minor"],
                         item["quantity"] * item["unit_price_minor"]),
                    )
                self._connection.execute(
                    "UPDATE commercial_opportunities SET stage='proposal',updated_at=? WHERE id=?",
                    (record["created_at"], record["opportunity_id"]),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(payload), previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return {"id": record["id"], "business_id": business_id, "subtotal_minor": subtotal, "status": "draft"}
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def list_commercial_quotes(
        self, *, opportunity_id: str | None = None, business_id: str | None = None
    ) -> tuple[dict[str, Any], ...]:
        if business_id is not None and business_id not in {"physical-agency", "physical-brand", "digital-products"}:
            raise ValueError("unknown commercial business unit")
        clauses, values = [], []
        if opportunity_id is not None:
            clauses.append("q.opportunity_id=?")
            values.append(opportunity_id)
        if business_id is not None:
            clauses.append("q.business_id=?")
            values.append(business_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                "SELECT q.*,o.customer_name FROM commercial_quotes q JOIN commercial_opportunities o ON o.id=q.opportunity_id"
                + where + " ORDER BY q.created_at DESC,q.id", tuple(values)
            ).fetchall()
            result = []
            for row in rows:
                items = self._connection.execute(
                    "SELECT * FROM commercial_quote_items WHERE quote_id=? ORDER BY id",
                    (row["id"],),
                ).fetchall()
                result.append({**dict(row), "items": [dict(item) for item in items]})
        return tuple(result)

    def update_commercial_quote_status(
        self, quote_id: str, status: str, acceptance_reference: str | None, audit: AuditRecord
    ) -> bool:
        if status not in {"approved_for_delivery", "accepted", "rejected", "void"}:
            raise ValueError("unsupported quote status")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                quote = self._connection.execute(
                    "SELECT status FROM commercial_quotes WHERE id=?", (quote_id,)
                ).fetchone()
                if quote is None:
                    self._connection.execute("ROLLBACK")
                    return False
                current = quote["status"]
                allowed = {
                    "draft": {"approved_for_delivery", "void"},
                    "approved_for_delivery": {"accepted", "rejected", "void"},
                    "accepted": {"void"},
                    "rejected": set(),
                    "void": set(),
                }
                if status not in allowed[current]:
                    raise ValueError("invalid quote status transition")
                if status == "accepted" and not (acceptance_reference and acceptance_reference.strip()):
                    raise ValueError("customer acceptance evidence reference is required")
                if status == "void" and current == "accepted":
                    existing_order = self._connection.execute(
                        "SELECT 1 FROM commercial_orders WHERE quote_id=?", (quote_id,)
                    ).fetchone()
                    if existing_order is not None:
                        raise ValueError("an accepted quote with an order record cannot be voided")
                self._connection.execute(
                    "UPDATE commercial_quotes SET status=?,acceptance_reference=?,updated_at=? WHERE id=?",
                    (status, acceptance_reference, datetime.now(timezone.utc).isoformat(), quote_id),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(payload), previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def create_commercial_order(self, order_id: str, quote_id: str, audit: AuditRecord) -> dict[str, Any]:
        """Record an order only from an accepted quote; no payment or fulfilment is triggered."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                quote = self._connection.execute(
                    """SELECT q.*,o.customer_name FROM commercial_quotes q
                       JOIN commercial_opportunities o ON o.id=q.opportunity_id WHERE q.id=?""",
                    (quote_id,),
                ).fetchone()
                if quote is None or quote["status"] != "accepted":
                    raise ValueError("an order requires a quote with recorded customer acceptance")
                existing_order = self._connection.execute(
                    "SELECT id FROM commercial_orders WHERE quote_id=?", (quote_id,)
                ).fetchone()
                if existing_order is not None:
                    raise ValueError("an order already exists for this quote")
                self._connection.execute(
                    """INSERT INTO commercial_orders
                       (id,quote_id,opportunity_id,business_id,customer_name,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,'awaiting_owner_fulfilment',?,?)""",
                    (order_id, quote_id, quote["opportunity_id"], quote["business_id"],
                     quote["customer_name"], datetime.now(timezone.utc).isoformat(),
                     datetime.now(timezone.utc).isoformat()),
                )
                self._connection.execute(
                    "UPDATE commercial_opportunities SET stage='won',updated_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), quote["opportunity_id"]),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(payload), previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return {"id": order_id, "quote_id": quote_id, "business_id": quote["business_id"], "status": "awaiting_owner_fulfilment"}
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def update_commercial_order_status(
        self, order_id: str, status: str, audit: AuditRecord
    ) -> bool:
        if status not in {"in_progress", "fulfilled", "cancelled"}:
            raise ValueError("unsupported order status")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                order = self._connection.execute(
                    "SELECT status FROM commercial_orders WHERE id=?", (order_id,)
                ).fetchone()
                if order is None:
                    self._connection.execute("ROLLBACK")
                    return False
                current = order["status"]
                allowed = {
                    "awaiting_owner_fulfilment": {"in_progress", "cancelled"},
                    "in_progress": {"fulfilled", "cancelled"},
                    "fulfilled": set(),
                    "cancelled": set(),
                }
                if status not in allowed[current]:
                    raise ValueError("invalid order status transition")
                self._connection.execute(
                    "UPDATE commercial_orders SET status=?,updated_at=? WHERE id=?",
                    (status, datetime.now(timezone.utc).isoformat(), order_id),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(payload), previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def list_commercial_orders(self, *, business_id: str | None = None) -> tuple[dict[str, Any], ...]:
        if business_id is not None and business_id not in {"physical-agency", "physical-brand", "digital-products"}:
            raise ValueError("unknown commercial business unit")
        sql = "SELECT * FROM commercial_orders"
        values: tuple[Any, ...] = ()
        if business_id is not None:
            sql += " WHERE business_id=?"
            values = (business_id,)
        sql += " ORDER BY created_at DESC,id"
        with self._lock:
            rows = self._connection.execute(sql, values).fetchall()
        return tuple(dict(row) for row in rows)
