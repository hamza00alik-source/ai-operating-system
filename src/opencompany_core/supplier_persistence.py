"""Supplier relationship persistence for physical commercial business units."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .domain import AuditRecord
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json


class SupplierPersistenceMixin:
    """Persist supplier relationships with business-unit and audit boundaries."""

    def create_commercial_supplier(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Create a private supplier relationship scoped to one physical business."""
        allowed = {("physical-agency", "agency_supplier"), ("physical-brand", "own_brand_supplier")}
        if (record.get("business_id"), record.get("relationship_type")) not in allowed:
            raise ValueError("supplier relationship type does not match its owning business")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO commercial_suppliers
                       (id,business_id,relationship_type,name,contact_name,email,phone,country,
                        product_categories_json,verification_status,notes,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record["id"], record["business_id"], record["relationship_type"],
                     record["name"], record.get("contact_name"), record.get("email"),
                     record.get("phone"), record.get("country"),
                     _json(record.get("product_categories", [])), "draft",
                     record.get("notes", ""), record["created_at"], record["updated_at"]),
                )
                previous = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
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

    def list_commercial_suppliers(self, *, business_id: str | None = None, limit: int = 500) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if business_id is not None and business_id not in {"physical-agency", "physical-brand"}:
            raise ValueError("supplier records are available only to physical business units")
        sql = "SELECT * FROM commercial_suppliers"
        values: list[Any] = []
        if business_id is not None:
            sql += " WHERE business_id=?"
            values.append(business_id)
        sql += " ORDER BY created_at DESC,id LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(sql, tuple(values)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["product_categories"] = json.loads(item.pop("product_categories_json"))
            result.append(item)
        return tuple(result)

    def update_commercial_supplier_status(self, supplier_id: str, status: str, audit: AuditRecord) -> bool:
        if status not in {"verified", "blocked"}:
            raise ValueError("supplier status must be verified or blocked")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    "UPDATE commercial_suppliers SET verification_status=?,updated_at=? WHERE id=? AND verification_status!='blocked'",
                    (status, datetime.now(timezone.utc).isoformat(), supplier_id),
                )
                if cursor.rowcount != 1:
                    self._connection.execute("ROLLBACK")
                    return False
                supplier = self._connection.execute("SELECT business_id FROM commercial_suppliers WHERE id=?", (supplier_id,)).fetchone()
                previous = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                details = dict(audit.details)
                details["business_id"] = supplier["business_id"]
                audited = AuditRecord(
                    id=audit.id, occurred_at=audit.occurred_at, actor_type=audit.actor_type,
                    actor_id=audit.actor_id, action=audit.action, subject_type=audit.subject_type,
                    subject_id=audit.subject_id, outcome=audit.outcome,
                    correlation_id=audit.correlation_id, details=details,
                )
                payload = _audit_payload(audited, previous_hash)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audited.id), audited.occurred_at.isoformat(), _json(payload), previous_hash, _digest(payload)),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
