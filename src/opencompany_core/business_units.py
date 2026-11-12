"""Owner-approved, isolated business-unit provisioning registry.

Provisioning creates a scoped business identity and separate namespace identifiers.
It deliberately does not activate workers, create external accounts, spend money,
publish offers, contact customers, or mark a venture as launched.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

_UNIT_TYPES = {
    "physical-agency", "physical-brand", "digital-products", "software",
    "services", "content-media", "licensing", "partnership", "other",
}
_DELIVERY_CLASSES = {
    "physical-goods", "digital-files", "software-access",
    "professional-service", "media-content", "license", "referral",
}
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_FOUNDATIONAL = (
    ("physical-agency", "physical-agency", "physical-goods"),
    ("physical-brand", "physical-brand", "physical-goods"),
    ("digital-products", "digital-products", "digital-files"),
)


class BusinessUnitProvisioningError(ValueError):
    """Invalid unit definition or missing owner authorization."""


class BusinessUnitRegistry:
    def __init__(self, connection: sqlite3.Connection, lock: RLock):
        self._db, self._lock = connection, lock
        with self._lock:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS opencompany_business_units (
                    business_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    unit_type TEXT NOT NULL,
                    delivery_class TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_market TEXT NOT NULL,
                    source_opportunity_id TEXT,
                    status TEXT NOT NULL CHECK(status IN ('foundational','provisioning','active','paused')),
                    namespace_id TEXT NOT NULL UNIQUE,
                    customer_scope_id TEXT NOT NULL UNIQUE,
                    finance_scope_id TEXT NOT NULL UNIQUE,
                    credential_scope_id TEXT NOT NULL UNIQUE,
                    integration_scope_id TEXT NOT NULL UNIQUE,
                    memory_scope_id TEXT NOT NULL UNIQUE,
                    asset_scope_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS opencompany_business_unit_events (
                    event_id TEXT PRIMARY KEY,
                    business_id TEXT NOT NULL REFERENCES opencompany_business_units(business_id),
                    action TEXT NOT NULL,
                    previous_status TEXT,
                    new_status TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    rationale TEXT,
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opencompany_units_status
                    ON opencompany_business_units(status, created_at);
                CREATE TRIGGER IF NOT EXISTS opencompany_unit_events_no_update
                    BEFORE UPDATE ON opencompany_business_unit_events
                    BEGIN SELECT RAISE(ABORT, 'business unit events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS opencompany_unit_events_no_delete
                    BEFORE DELETE ON opencompany_business_unit_events
                    BEGIN SELECT RAISE(ABORT, 'business unit events are append-only'); END;
            """)
            now = datetime.now(timezone.utc).isoformat()
            for business_id, unit_type, delivery_class in _FOUNDATIONAL:
                self._db.execute(
                    """INSERT OR IGNORE INTO opencompany_business_units
                    (business_id,name,unit_type,delivery_class,description,target_market,
                     source_opportunity_id,status,namespace_id,customer_scope_id,finance_scope_id,
                     credential_scope_id,integration_scope_id,memory_scope_id,asset_scope_id,
                     created_at,updated_at)
                    VALUES(?,?,?,?,?,?,NULL,'foundational',?,?,?,?,?,?,?, ?,?)""",
                    (business_id, business_id.replace("-", " ").title(), unit_type,
                     delivery_class, "Foundational OpenCompany business; existing operating scope retained.",
                     "Existing approved market", str(uuid4()), str(uuid4()), str(uuid4()),
                     str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), now, now),
                )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def list(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 500:
            raise BusinessUnitProvisioningError("limit must be between 1 and 500")
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM opencompany_business_units ORDER BY created_at,business_id LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def get(self, business_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM opencompany_business_units WHERE business_id=?", (business_id,)
            ).fetchone()
        return self._decode(row) if row else None

    def provision_from_opportunity(
        self, portfolio: Any, opportunity_id: str, *, business_id: str, name: str,
        unit_type: str, delivery_class: str, description: str, target_market: str,
        confirm_owner_approval: bool,
    ) -> dict[str, Any]:
        if not confirm_owner_approval:
            raise BusinessUnitProvisioningError("explicit owner approval is required to provision a business unit")
        if not _SLUG.fullmatch(business_id):
            raise BusinessUnitProvisioningError("business_id must be a 2-63 character lowercase slug")
        if unit_type not in _UNIT_TYPES:
            raise BusinessUnitProvisioningError("unsupported business unit type")
        if delivery_class not in _DELIVERY_CLASSES:
            raise BusinessUnitProvisioningError("unsupported primary delivery class")
        for value, label, maximum in (
            (name, "name", 160), (description, "description", 5000),
            (target_market, "target market", 300),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise BusinessUnitProvisioningError(f"{label} is empty or too long")
        opportunity = portfolio.get(opportunity_id)
        if opportunity is None:
            raise BusinessUnitProvisioningError("source opportunity was not found")
        if opportunity["status"] != "approved_to_launch":
            raise BusinessUnitProvisioningError("only opportunities approved for launch planning can be provisioned")
        now = datetime.now(timezone.utc).isoformat()
        scopes = [str(uuid4()) for _ in range(7)]
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    """INSERT INTO opencompany_business_units
                    (business_id,name,unit_type,delivery_class,description,target_market,
                     source_opportunity_id,status,namespace_id,customer_scope_id,finance_scope_id,
                     credential_scope_id,integration_scope_id,memory_scope_id,asset_scope_id,
                     created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,'provisioning',?,?,?,?,?,?,?,?,?)""",
                    (business_id, name.strip(), unit_type, delivery_class, description.strip(),
                     target_market.strip(), opportunity_id, *scopes, now, now),
                )
                self._db.execute(
                    """INSERT INTO opencompany_business_unit_events
                    (event_id,business_id,action,previous_status,new_status,actor,rationale,occurred_at)
                    VALUES(?,?,'provisioned',NULL,'provisioning','owner',?,?)""",
                    (str(uuid4()), business_id,
                     "Created isolated internal scopes from owner-approved opportunity; external activation remains disabled.",
                     now),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise BusinessUnitProvisioningError("business_id already exists; choose a unique identifier") from exc
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        return self.get(business_id)

    def events(self, business_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM opencompany_business_unit_events WHERE business_id=? ORDER BY occurred_at,event_id",
                (business_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)
