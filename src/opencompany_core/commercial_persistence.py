"""Commercial-domain SQLite repository operations mixed into SQLiteStore."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .domain import AuditRecord
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json


class CommercialPersistenceMixin:
    """Commercial records share the store's connection, lock and audit transaction."""

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
