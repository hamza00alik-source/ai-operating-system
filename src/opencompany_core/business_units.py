"""Owner-approved, isolated business-unit provisioning registry.

Provisioning creates a scoped business identity and separate namespace identifiers.
It deliberately does not activate workers, create external accounts, spend money,
publish offers, contact customers, or mark a venture as launched.
"""
from __future__ import annotations

import os
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
        if business_id == "core":
            raise BusinessUnitProvisioningError("core is reserved for internal OpenCompany operations")
        if unit_type not in _UNIT_TYPES:
            raise BusinessUnitProvisioningError("unsupported business unit type")
        if delivery_class not in _DELIVERY_CLASSES:
            raise BusinessUnitProvisioningError("unsupported primary delivery class")
        required_delivery = {
            "physical-agency": "physical-goods",
            "physical-brand": "physical-goods",
            "digital-products": "digital-files",
        }.get(unit_type)
        if required_delivery is not None and delivery_class != required_delivery:
            raise BusinessUnitProvisioningError(
                f"{unit_type} must use {required_delivery} delivery; cross-type fulfilment is prohibited"
            )
        for value, label, maximum in (
            (name, "name", 160), (description, "description", 5000),
            (target_market, "target market", 300),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise BusinessUnitProvisioningError(f"{label} is empty or too long")
        now = datetime.now(timezone.utc).isoformat()
        scopes = [str(uuid4()) for _ in range(7)]
        with self._lock:
            opportunity = portfolio.get(opportunity_id)
            if opportunity is None:
                raise BusinessUnitProvisioningError("source opportunity was not found")
            if opportunity["status"] != "approved_to_launch":
                raise BusinessUnitProvisioningError("only opportunities approved for launch planning can be provisioned")
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

    def require_operational(self, business_id: str) -> dict[str, Any]:
        """Resolve an operational unit or fail closed for unknown/provisioning units."""
        unit = self.get(business_id)
        if unit is None:
            raise BusinessUnitProvisioningError("unknown business unit; provision it through an approved venture first")
        if unit["status"] not in {"foundational", "active"}:
            raise BusinessUnitProvisioningError(
                "business unit is not operational; provisioning must be completed and owner-approved before work is assigned"
            )
        return unit

    def scope_for(self, business_id: str) -> dict[str, str]:
        """Return opaque namespace identifiers only after operational status is confirmed."""
        unit = self.require_operational(business_id)
        return {
            key: unit[key] for key in (
                "namespace_id", "customer_scope_id", "finance_scope_id",
                "credential_scope_id", "integration_scope_id", "memory_scope_id",
                "asset_scope_id",
            )
        }


    def activation_readiness(self, business_id: str) -> dict[str, Any]:
        """Return a fail-closed, evidence-based activation report without changing state."""
        unit = self.get(business_id)
        if unit is None:
            raise BusinessUnitProvisioningError("unknown business unit")
        if unit["status"] == "foundational":
            return {
                "business_id": business_id,
                "status": "foundational_operational",
                "activation_allowed": True,
                "blockers": [],
                "checks": [{"key": "foundational_unit", "ready": True,
                            "evidence": "Existing foundational operating unit; no activation transition required."}],
            }
        if unit["status"] == "active":
            return {
                "business_id": business_id,
                "status": "active",
                "activation_allowed": True,
                "blockers": [],
                "checks": [{"key": "unit_active", "ready": True,
                            "evidence": "Registry status is already active."}],
            }

        checks: list[dict[str, Any]] = []
        blockers: list[str] = []
        scope_keys = (
            "namespace_id", "customer_scope_id", "finance_scope_id",
            "credential_scope_id", "integration_scope_id", "memory_scope_id",
            "asset_scope_id",
        )
        scopes_complete = all(bool(unit.get(key)) for key in scope_keys) and len(
            {unit.get(key) for key in scope_keys}
        ) == len(scope_keys)
        checks.append({
            "key": "unique_scope_identifiers",
            "ready": scopes_complete,
            "evidence": "Seven distinct internal scope identifiers are present." if scopes_complete
                        else "One or more required scope identifiers are missing or duplicated.",
        })
        if not scopes_complete:
            blockers.append("unique_scope_identifiers")

        with self._lock:
            tables = {
                row["name"]: row["sql"] or ""
                for row in self._db.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE 'commercial_%'"
                ).fetchall()
            }
            columns = {
                name: {row["name"] for row in self._db.execute(
                    f'PRAGMA table_info("{name}")'
                ).fetchall()}
                for name in tables
            }
            customer_tables = {
                "commercial_opportunities", "commercial_quotes", "commercial_orders"
            }
            customer_scope_ready = customer_tables.issubset(tables)
            customer_scope_evidence = []
            for table_name in sorted(customer_tables):
                if table_name not in tables or not {
                    "business_id", "customer_scope_id"
                }.issubset(columns.get(table_name, set())):
                    customer_scope_ready = False
                    customer_scope_evidence.append(f"{table_name}: missing scope columns")
                    continue
                foreign_keys = self._db.execute(
                    f'PRAGMA foreign_key_list("{table_name}")'
                ).fetchall()
                grouped: dict[int, list[tuple[str, str]]] = {}
                for fk in foreign_keys:
                    grouped.setdefault(fk["id"], []).append((fk["from"], fk["to"]))
                required_pair = {("business_id", "business_id"),
                                 ("customer_scope_id", "customer_scope_id")}
                pair_found = any(
                    fk["table"] == "opencompany_business_units"
                    and set(pairs) == required_pair
                    for fk_id, pairs in grouped.items()
                    for fk in foreign_keys if fk["id"] == fk_id
                )
                if not pair_found:
                    customer_scope_ready = False
                    customer_scope_evidence.append(f"{table_name}: missing composite unit/scope foreign key")
            finance_tables = {
                row["name"]: row["sql"] or ""
                for row in self._db.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='table' "
                    "AND name IN ('opencompany_finance_entries','opencompany_finance_entry_events')"
                ).fetchall()
            }
            finance_columns = {
                name: {row["name"] for row in self._db.execute(
                    f'PRAGMA table_info("{name}")'
                ).fetchall()}
                for name in finance_tables
            }
            finance_fks = {
                name: self._db.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()
                for name in finance_tables
            }
            finance_triggers = {
                row["name"] for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('opencompany_finance_entries_no_update','opencompany_finance_entries_no_delete',"
                    "'opencompany_finance_entry_events_no_update','opencompany_finance_entry_events_no_delete',"
                    "'opencompany_business_units_finance_scope_no_update')"
                ).fetchall()
            }
            credential_tables = {
                row["name"]: row["sql"] or ""
                for row in self._db.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='table' "
                    "AND name IN ('opencompany_business_credentials','opencompany_business_credential_events')"
                ).fetchall()
            }
            credential_columns = {
                name: {row["name"] for row in self._db.execute(
                    f'PRAGMA table_info("{name}")'
                ).fetchall()}
                for name in credential_tables
            }
            credential_fks = {
                name: self._db.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()
                for name in credential_tables
            }
            credential_triggers = {
                row["name"] for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('opencompany_business_credential_events_no_update',"
                    "'opencompany_business_credential_events_no_delete',"
                    "'opencompany_business_units_credential_scope_no_update')"
                ).fetchall()
            }
            integration_tables = {
                row["name"]: row["sql"] or ""
                for row in self._db.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='table' "
                    "AND name IN ('opencompany_business_integrations','opencompany_business_integration_events')"
                ).fetchall()
            }
            integration_columns = {
                name: {row["name"] for row in self._db.execute(
                    f'PRAGMA table_info("{name}")'
                ).fetchall()}
                for name in integration_tables
            }
            integration_fks = {
                name: self._db.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()
                for name in integration_tables
            }
            integration_triggers = {
                row["name"] for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('opencompany_business_integration_events_no_update',"
                    "'opencompany_business_integration_events_no_delete',"
                    "'opencompany_business_integrations_no_scope_change',"
                    "'opencompany_business_units_integration_scope_no_update')"
                ).fetchall()
            }

        constrained = sorted(
            name for name, sql in tables.items()
            if "business_id" in columns[name] and "CHECK" in sql.upper()
            and "BUSINESS_ID IN" in sql.upper()
        )
        commercial_dynamic = bool(tables) and not constrained
        checks.append({
            "key": "commercial_persistence_dynamic_business_ids",
            "ready": commercial_dynamic,
            "evidence": (
                "Commercial tables do not contain a fixed business_id allowlist."
                if commercial_dynamic else
                "Commercial schema still contains fixed business_id allowlists: " + ", ".join(constrained)
            ),
        })
        if not commercial_dynamic:
            blockers.append("commercial_persistence_dynamic_business_ids")

        checks.append({
            "key": "customer_scope_enforcement",
            "ready": customer_scope_ready,
            "evidence": (
                "Opportunities, quotes, and orders persist customer_scope_id and enforce "
                "business_id/customer_scope_id pairing plus same-scope parent relationships."
                if customer_scope_ready else
                "Customer scope enforcement is incomplete: " + "; ".join(customer_scope_evidence)
            ),
        })
        if not customer_scope_ready:
            blockers.append("customer_scope_enforcement")

        expected_finance = {"opencompany_finance_entries", "opencompany_finance_entry_events"}
        unit_pair = {("business_id", "business_id"), ("finance_scope_id", "finance_scope_id")}
        entries_pair = any(
            fk["table"] == "opencompany_business_units"
            and {(x["from"], x["to"]) for x in finance_fks.get("opencompany_finance_entries", [])
                 if x["id"] == fk["id"]} == unit_pair
            for fk in finance_fks.get("opencompany_finance_entries", [])
        )
        events_unit_pair = any(
            fk["table"] == "opencompany_business_units"
            and {(x["from"], x["to"]) for x in finance_fks.get("opencompany_finance_entry_events", [])
                 if x["id"] == fk["id"]} == unit_pair
            for fk in finance_fks.get("opencompany_finance_entry_events", [])
        )
        event_entry_pair = any(
            fk["table"] == "opencompany_finance_entries"
            and {(x["from"], x["to"]) for x in finance_fks.get("opencompany_finance_entry_events", [])
                 if x["id"] == fk["id"]} == {
                     ("entry_id", "id"), ("business_id", "business_id"),
                     ("finance_scope_id", "finance_scope_id")
                 }
            for fk in finance_fks.get("opencompany_finance_entry_events", [])
        )
        append_only_triggers = {
            "opencompany_finance_entries_no_update", "opencompany_finance_entries_no_delete",
            "opencompany_finance_entry_events_no_update", "opencompany_finance_entry_events_no_delete",
            "opencompany_business_units_finance_scope_no_update",
        }.issubset(finance_triggers)
        finance_ready = (
            expected_finance.issubset(finance_tables)
            and {"business_id", "finance_scope_id", "amount_minor", "currency", "entry_type"}
                .issubset(finance_columns.get("opencompany_finance_entries", set()))
            and {"entry_id", "business_id", "finance_scope_id", "action", "actor_type"}
                .issubset(finance_columns.get("opencompany_finance_entry_events", set()))
            and entries_pair and events_unit_pair and event_entry_pair and append_only_triggers
        )
        checks.append({
            "key": "finance_ledger_scope",
            "ready": finance_ready,
            "evidence": (
                "OpenCompany finance entries and review events enforce business/finance-scope "
                "pairing, same-scope entry/event relationships, and database-level append-only triggers."
                if finance_ready else
                "Finance ledger enforcement is incomplete: both scoped tables, composite foreign keys, "
                "required columns, four ledger append-only triggers, and the immutable registry finance-scope trigger must be present."
            ),
        })
        if not finance_ready:
            blockers.append("finance_ledger_scope")

        credential_pair = any(
            fk["table"] == "opencompany_business_units"
            and {(x["from"], x["to"]) for x in credential_fks.get("opencompany_business_credentials", [])
                 if x["id"] == fk["id"]} == {
                     ("business_id", "business_id"), ("credential_scope_id", "credential_scope_id")
                 }
            for fk in credential_fks.get("opencompany_business_credentials", [])
        )
        credential_events_pair = any(
            fk["table"] == "opencompany_business_units"
            and {(x["from"], x["to"]) for x in credential_fks.get("opencompany_business_credential_events", [])
                 if x["id"] == fk["id"]} == {
                     ("business_id", "business_id"), ("credential_scope_id", "credential_scope_id")
                 }
            for fk in credential_fks.get("opencompany_business_credential_events", [])
        )
        credential_history_ready = {
            "opencompany_business_credential_events_no_update",
            "opencompany_business_credential_events_no_delete",
            "opencompany_business_units_credential_scope_no_update",
        }.issubset(credential_triggers)
        credential_ready = (
            {"opencompany_business_credentials", "opencompany_business_credential_events"}
                .issubset(credential_tables)
            and {"business_id", "credential_scope_id", "credential_key", "nonce", "ciphertext", "revision"}
                .issubset(credential_columns.get("opencompany_business_credentials", set()))
            and {"business_id", "credential_scope_id", "credential_key", "action", "revision"}
                .issubset(credential_columns.get("opencompany_business_credential_events", set()))
            and credential_pair and credential_events_pair and credential_history_ready
            and len(os.environ.get("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "").strip()) >= 32
        )
        checks.append({
            "key": "credential_scope_adapter",
            "ready": credential_ready,
            "evidence": (
                "Encrypted business-specific credentials are stored under composite business/credential scopes; "
                "change history is append-only, the registry credential scope is immutable, and the dedicated encryption key is configured."
                if credential_ready else
                "Credential isolation requires encrypted credential storage, scoped foreign keys, "
                "append-only change history, and an immutable registry scope."
            ),
        })
        if not credential_ready:
            blockers.append("credential_scope_adapter")

        integration_unit_pair = any(
            fk["table"] == "opencompany_business_units"
            and {(x["from"], x["to"]) for x in integration_fks.get("opencompany_business_integrations", [])
                 if x["id"] == fk["id"]} == {
                     ("business_id", "business_id"), ("integration_scope_id", "integration_scope_id")
                 }
            for fk in integration_fks.get("opencompany_business_integrations", [])
        )
        integration_credential_pair = any(
            fk["table"] == "opencompany_business_credentials"
            and {(x["from"], x["to"]) for x in integration_fks.get("opencompany_business_integrations", [])
                 if x["id"] == fk["id"]} == {
                     ("business_id", "business_id"), ("credential_scope_id", "credential_scope_id"),
                     ("credential_key", "credential_key")
                 }
            for fk in integration_fks.get("opencompany_business_integrations", [])
        )
        integration_event_pair = any(
            fk["table"] == "opencompany_business_units"
            and {(x["from"], x["to"]) for x in integration_fks.get("opencompany_business_integration_events", [])
                 if x["id"] == fk["id"]} == {
                     ("business_id", "business_id"), ("integration_scope_id", "integration_scope_id")
                 }
            for fk in integration_fks.get("opencompany_business_integration_events", [])
        )
        integration_history_ready = {
            "opencompany_business_integration_events_no_update",
            "opencompany_business_integration_events_no_delete",
            "opencompany_business_integrations_no_scope_change",
            "opencompany_business_units_integration_scope_no_update",
        }.issubset(integration_triggers)
        integration_ready = (
            {"opencompany_business_integrations", "opencompany_business_integration_events"}
                .issubset(integration_tables)
            and {"integration_id", "business_id", "integration_scope_id", "provider_key",
                 "credential_scope_id", "credential_key", "permissions_json", "status"}
                .issubset(integration_columns.get("opencompany_business_integrations", set()))
            and {"integration_id", "business_id", "integration_scope_id", "action", "actor_type"}
                .issubset(integration_columns.get("opencompany_business_integration_events", set()))
            and integration_unit_pair and integration_credential_pair and integration_event_pair
            and integration_history_ready
        )
        checks.append({
            "key": "integration_scope_adapter",
            "ready": integration_ready,
            "evidence": (
                "Integration declarations are isolated by business/integration scope, bound to a credential "
                "from the same business, and protected by append-only history and immutable scope identifiers. "
                "Registration does not connect or execute the integration."
                if integration_ready else
                "Integration isolation requires scoped registry tables, a same-business credential foreign key, "
                "append-only history, and immutable integration scope identifiers."
            ),
        })
        if not integration_ready:
            blockers.append("integration_scope_adapter")
        blockers.append("integration_execution_adapter")
        checks.append({
            "key": "integration_execution_adapter",
            "ready": False,
            "evidence": "External integration execution, permission enforcement, connection testing, and per-action owner approval are deliberately not enabled by the registry-only increment.",
        })

        for key, label in (
            ("memory_scope_id", "memory_scope_adapter"),
            ("asset_scope_id", "asset_scope_adapter"),
        ):
            blockers.append(key.replace("_scope_id", "_scope_adapter"))
            checks.append({
                "key": key.replace("_scope_id", "_scope_adapter"),
                "ready": False,
                "evidence": f"{label} is recorded as an identifier only; an enforcing adapter is not registered by this readiness gate.",
            })

        blockers.append("owner_activation_approval")
        checks.append({
            "key": "owner_activation_approval",
            "ready": False,
            "evidence": "A separate activation approval and audited status transition have not been implemented.",
        })
        return {
            "business_id": business_id,
            "status": unit["status"],
            "activation_allowed": not blockers,
            "blockers": blockers,
            "checks": checks,
        }

    def events(self, business_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM opencompany_business_unit_events WHERE business_id=? ORDER BY occurred_at,event_id",
                (business_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)
