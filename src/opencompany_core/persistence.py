"""Local durable storage for the independent OpenCompany core.

SQLite is used as a small, inspectable persistence layer. All writes are
transactional; audit events are linked with SHA-256 hashes to make later
alteration detectable. This is tamper-evident, not a substitute for backups
or access controls.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from .domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem


_ZERO_HASH = "0" * 64
_SCHEMA_VERSION = 16

_WORK_ITEM_BUSINESS_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def _registered_operational_unit(
    connection: sqlite3.Connection, lock: RLock, business_id: str,
) -> dict[str, Any]:
    """Read operational eligibility without running DDL inside a caller transaction."""
    if not isinstance(business_id, str) or not _WORK_ITEM_BUSINESS_ID.fullmatch(business_id):
        raise ValueError("business_id must be a 2-63 character lowercase slug")
    with lock:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='opencompany_business_units'"
        ).fetchone()
        if exists is None:
            if connection.in_transaction:
                raise ValueError("business-unit registry must be initialized before transactional writes")
            from .business_units import BusinessUnitRegistry
            BusinessUnitRegistry(connection, lock)
        row = connection.execute(
            "SELECT * FROM opencompany_business_units WHERE business_id=?", (business_id,)
        ).fetchone()
    if row is None:
        raise ValueError("unknown business unit; provision it through an approved venture first")
    unit = dict(row)
    if unit["status"] not in {"foundational", "active"}:
        raise ValueError("business unit is not operational; provisioning must be completed and owner-approved before work is assigned")
    return unit


def _assert_operational_work_item_scope(
    connection: sqlite3.Connection, lock: RLock, business_id: str,
) -> None:
    """Validate work-item business identity at the persistence boundary."""
    if business_id == "core":
        return
    _registered_operational_unit(connection, lock, business_id)


def _assert_operational_commercial_scope(
    connection: sqlite3.Connection, lock: RLock, business_id: str,
) -> dict[str, Any]:
    """Require an existing, operational registry unit at every commercial write boundary."""
    return _registered_operational_unit(connection, lock, business_id)


def _migrate_v7_commercial_business_ids(connection: sqlite3.Connection) -> None:
    """Rebuild commercial tables without fixed business-ID allowlists.

    Foreign keys are disabled only around this atomic table-rebuild migration.
    Child table definitions, existing rows, indexes, and user triggers are retained.
    """
    tables = {
        "commercial_opportunities": (
            """CREATE TABLE commercial_opportunities_v8 (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_contact TEXT,
                customer_need TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'new' CHECK(stage IN ('new','qualified','proposal','won','lost','on_hold')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "id,business_id,customer_name,customer_contact,customer_need,stage,created_at,updated_at",
            "idx_commercial_opportunities_unit",
            "business_id, created_at",
        ),
        "commercial_products": (
            """CREATE TABLE commercial_products_v8 (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','archived')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "id,business_id,name,description,category,status,created_at,updated_at",
            "idx_commercial_products_unit",
            "business_id, status, created_at",
        ),
        "commercial_quotes": (
            """CREATE TABLE commercial_quotes_v8 (
                id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL REFERENCES commercial_opportunities(id),
                business_id TEXT NOT NULL,
                title TEXT NOT NULL,
                currency TEXT NOT NULL CHECK(length(currency)=3),
                currency_exponent INTEGER NOT NULL CHECK(currency_exponent BETWEEN 0 AND 3),
                subtotal_minor INTEGER NOT NULL CHECK(subtotal_minor > 0),
                terms TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved_for_delivery','accepted','rejected','void')),
                acceptance_reference TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "id,opportunity_id,business_id,title,currency,currency_exponent,subtotal_minor,terms,status,acceptance_reference,created_at,updated_at",
            "idx_commercial_quotes_scope",
            "business_id, opportunity_id, created_at",
        ),
        "commercial_orders": (
            """CREATE TABLE commercial_orders_v8 (
                id TEXT PRIMARY KEY,
                quote_id TEXT NOT NULL UNIQUE REFERENCES commercial_quotes(id),
                opportunity_id TEXT NOT NULL REFERENCES commercial_opportunities(id),
                business_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'awaiting_owner_fulfilment' CHECK(status IN ('awaiting_owner_fulfilment','in_progress','fulfilled','cancelled')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "id,quote_id,opportunity_id,business_id,customer_name,status,created_at,updated_at",
            "idx_commercial_orders_scope",
            "business_id, status, created_at",
        ),
        "commercial_suppliers": (
            """CREATE TABLE commercial_suppliers_v8 (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL CHECK(relationship_type IN ('agency_supplier','own_brand_supplier','supplier')),
                name TEXT NOT NULL,
                contact_name TEXT,
                email TEXT,
                phone TEXT,
                country TEXT,
                product_categories_json TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'draft' CHECK(verification_status IN ('draft','verified','blocked')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK((business_id='physical-agency' AND relationship_type='agency_supplier')
                   OR (business_id='physical-brand' AND relationship_type='own_brand_supplier')
                   OR (business_id NOT IN ('physical-agency','physical-brand') AND relationship_type='supplier'))
            )""",
            "id,business_id,relationship_type,name,contact_name,email,phone,country,product_categories_json,verification_status,notes,created_at,updated_at",
            "idx_commercial_suppliers_scope",
            "business_id, verification_status, created_at",
        ),
    }
    expected = set(tables)
    present = {
        row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'commercial_%'"
        ).fetchall()
    }
    if not expected.issubset(present):
        raise RuntimeError("schema v7 migration requires all commercial tables; no changes were made")
    trigger_sql = [
        row["sql"] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('commercial_opportunities','commercial_products',"
            "'commercial_quotes','commercial_orders','commercial_suppliers') "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    index_sql = [
        row["sql"] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name IN ('commercial_opportunities','commercial_products',"
            "'commercial_quotes','commercial_orders','commercial_suppliers') "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    for name in expected:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (f"{name}_v8",),
        ).fetchone():
            raise RuntimeError(f"schema v7 migration found an unexpected staging table: {name}_v8")

    if connection.in_transaction:
        raise RuntimeError("schema migration cannot run inside an existing transaction")
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        before = {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in expected
        }
        for name, (ddl, columns, _, _) in tables.items():
            connection.execute(ddl)
            connection.execute(
                f"INSERT INTO {name}_v8 ({columns}) SELECT {columns} FROM {name}"
            )
            copied = int(connection.execute(f"SELECT COUNT(*) FROM {name}_v8").fetchone()[0])
            if copied != before[name]:
                raise RuntimeError(f"schema migration row-count mismatch for {name}")
        for name in tables:
            connection.execute(f"DROP TABLE {name}")
        for name in tables:
            connection.execute(f"ALTER TABLE {name}_v8 RENAME TO {name}")
        for statement in index_sql:
            connection.execute(statement)
        for statement in trigger_sql:
            connection.execute(statement)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("schema migration produced foreign-key violations")
        connection.execute("PRAGMA user_version = 8")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign-key enforcement could not be restored after schema migration")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("schema migration failed post-commit foreign-key validation")


def _migrate_v8_customer_scopes(connection: sqlite3.Connection) -> None:
    """Backfill customer scopes and enforce business/scope pairing in the database."""
    from .business_units import BusinessUnitRegistry

    if connection.in_transaction:
        raise RuntimeError("customer-scope migration cannot run inside an existing transaction")
    registry = BusinessUnitRegistry(connection, RLock())
    registry_units = registry.list()
    if not registry_units:
        raise RuntimeError("customer-scope migration requires registered business units")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_opencompany_unit_customer_scope "
        "ON opencompany_business_units(business_id, customer_scope_id)"
    )
    definitions = {
        "commercial_opportunities": (
            """CREATE TABLE commercial_opportunities_v9 (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                customer_scope_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_contact TEXT,
                customer_need TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'new' CHECK(stage IN ('new','qualified','proposal','won','lost','on_hold')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(id,business_id,customer_scope_id),
                FOREIGN KEY(business_id,customer_scope_id)
                    REFERENCES opencompany_business_units(business_id,customer_scope_id)
            )""",
            """INSERT INTO commercial_opportunities_v9
               (id,business_id,customer_scope_id,customer_name,customer_contact,customer_need,stage,created_at,updated_at)
               SELECT o.id,o.business_id,u.customer_scope_id,o.customer_name,o.customer_contact,
                      o.customer_need,o.stage,o.created_at,o.updated_at
               FROM commercial_opportunities o
               JOIN opencompany_business_units u ON u.business_id=o.business_id""",
            "idx_commercial_opportunities_unit",
            "business_id, created_at",
        ),
        "commercial_quotes": (
            """CREATE TABLE commercial_quotes_v9 (
                id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                business_id TEXT NOT NULL,
                customer_scope_id TEXT NOT NULL,
                title TEXT NOT NULL,
                currency TEXT NOT NULL CHECK(length(currency)=3),
                currency_exponent INTEGER NOT NULL CHECK(currency_exponent BETWEEN 0 AND 3),
                subtotal_minor INTEGER NOT NULL CHECK(subtotal_minor > 0),
                terms TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved_for_delivery','accepted','rejected','void')),
                acceptance_reference TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(id,business_id,customer_scope_id),
                FOREIGN KEY(business_id,customer_scope_id)
                    REFERENCES opencompany_business_units(business_id,customer_scope_id),
                FOREIGN KEY(opportunity_id,business_id,customer_scope_id)
                    REFERENCES commercial_opportunities(id,business_id,customer_scope_id)
            )""",
            """INSERT INTO commercial_quotes_v9
               (id,opportunity_id,business_id,customer_scope_id,title,currency,currency_exponent,
                subtotal_minor,terms,status,acceptance_reference,created_at,updated_at)
               SELECT q.id,q.opportunity_id,q.business_id,u.customer_scope_id,q.title,q.currency,
                      q.currency_exponent,q.subtotal_minor,q.terms,q.status,q.acceptance_reference,
                      q.created_at,q.updated_at
               FROM commercial_quotes q
               JOIN opencompany_business_units u ON u.business_id=q.business_id""",
            "idx_commercial_quotes_scope",
            "business_id, opportunity_id, created_at",
        ),
        "commercial_orders": (
            """CREATE TABLE commercial_orders_v9 (
                id TEXT PRIMARY KEY,
                quote_id TEXT NOT NULL,
                opportunity_id TEXT NOT NULL,
                business_id TEXT NOT NULL,
                customer_scope_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'awaiting_owner_fulfilment' CHECK(status IN ('awaiting_owner_fulfilment','in_progress','fulfilled','cancelled')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(business_id,customer_scope_id)
                    REFERENCES opencompany_business_units(business_id,customer_scope_id),
                FOREIGN KEY(quote_id,business_id,customer_scope_id)
                    REFERENCES commercial_quotes(id,business_id,customer_scope_id),
                FOREIGN KEY(opportunity_id,business_id,customer_scope_id)
                    REFERENCES commercial_opportunities(id,business_id,customer_scope_id)
            )""",
            """INSERT INTO commercial_orders_v9
               (id,quote_id,opportunity_id,business_id,customer_scope_id,customer_name,status,created_at,updated_at)
               SELECT o.id,o.quote_id,o.opportunity_id,o.business_id,u.customer_scope_id,
                      o.customer_name,o.status,o.created_at,o.updated_at
               FROM commercial_orders o
               JOIN opencompany_business_units u ON u.business_id=o.business_id""",
            "idx_commercial_orders_scope",
            "business_id, status, created_at",
        ),
    }
    triggers = [
        row["sql"] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('commercial_opportunities','commercial_quotes','commercial_orders') "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    indexes = [
        row["sql"] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name IN ('commercial_opportunities','commercial_quotes','commercial_orders') "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    for name in definitions:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (f"{name}_v9",),
        ).fetchone():
            raise RuntimeError(f"customer-scope migration found an unexpected staging table: {name}_v9")
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        before = {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in definitions
        }
        for name, (ddl, copy_sql, _, _) in definitions.items():
            connection.execute(ddl)
            connection.execute(copy_sql)
            copied = int(connection.execute(f"SELECT COUNT(*) FROM {name}_v9").fetchone()[0])
            if copied != before[name]:
                raise RuntimeError(
                    f"customer-scope migration could not map every {name} row to a registered unit"
                )
        for name in ("commercial_orders", "commercial_quotes", "commercial_opportunities"):
            connection.execute(f"DROP TABLE {name}")
        for name in ("commercial_opportunities", "commercial_quotes", "commercial_orders"):
            connection.execute(f"ALTER TABLE {name}_v9 RENAME TO {name}")
        for statement in indexes:
            connection.execute(statement)
        for statement in triggers:
            connection.execute(statement)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("customer-scope migration produced foreign-key violations")
        connection.execute("PRAGMA user_version = 9")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign-key enforcement could not be restored after customer-scope migration")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("customer-scope migration failed post-commit foreign-key validation")



def _migrate_v9_finance_ledger(connection: sqlite3.Connection) -> None:
    """Create the OpenCompany-native, business-scoped append-only finance ledger."""
    if connection.in_transaction:
        raise RuntimeError("finance-ledger migration cannot run inside an existing transaction")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_opencompany_unit_finance_scope "
        "ON opencompany_business_units(business_id,finance_scope_id)"
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("""
            CREATE TABLE opencompany_finance_entries (
                id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                finance_scope_id TEXT NOT NULL,
                entry_type TEXT NOT NULL CHECK(entry_type IN ('revenue','expense','refund','adjustment')),
                amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                currency TEXT NOT NULL CHECK(length(currency)=3 AND currency=upper(currency)),
                description TEXT NOT NULL CHECK(length(trim(description)) BETWEEN 1 AND 2000),
                source_reference TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(id,business_id,finance_scope_id),
                FOREIGN KEY(business_id,finance_scope_id)
                    REFERENCES opencompany_business_units(business_id,finance_scope_id)
            )
        """)
        connection.execute("""
            CREATE INDEX idx_opencompany_finance_entries_scope
            ON opencompany_finance_entries(business_id,created_at,id)
        """)
        connection.execute("""
            CREATE TABLE opencompany_finance_entry_events (
                event_id TEXT PRIMARY KEY,
                entry_id TEXT NOT NULL,
                business_id TEXT NOT NULL,
                finance_scope_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('recorded','owner_verified','owner_rejected','owner_approved')),
                actor_type TEXT NOT NULL CHECK(actor_type IN ('system','owner')),
                actor_id TEXT,
                rationale TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(business_id,finance_scope_id)
                    REFERENCES opencompany_business_units(business_id,finance_scope_id),
                FOREIGN KEY(entry_id,business_id,finance_scope_id)
                    REFERENCES opencompany_finance_entries(id,business_id,finance_scope_id)
            )
        """)
        connection.execute("""
            CREATE INDEX idx_opencompany_finance_events_entry
            ON opencompany_finance_entry_events(entry_id,occurred_at,event_id)
        """)
        for table in ("opencompany_finance_entries", "opencompany_finance_entry_events"):
            connection.execute(f"""
                CREATE TRIGGER {table}_no_update
                BEFORE UPDATE ON {table}
                BEGIN SELECT RAISE(ABORT, 'finance ledger records are append-only'); END
            """)
            connection.execute(f"""
                CREATE TRIGGER {table}_no_delete
                BEFORE DELETE ON {table}
                BEGIN SELECT RAISE(ABORT, 'finance ledger records are append-only'); END
            """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_units_finance_scope_no_update
            BEFORE UPDATE OF finance_scope_id ON opencompany_business_units
            BEGIN SELECT RAISE(ABORT, 'business-unit finance scope is immutable'); END
        """)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("finance-ledger migration produced foreign-key violations")
        connection.execute("PRAGMA user_version = 10")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign-key enforcement is disabled after finance-ledger migration")



def _migrate_v10_business_credentials(connection: sqlite3.Connection) -> None:
    """Create encrypted, business-scoped credential storage and immutable history."""
    if connection.in_transaction:
        raise RuntimeError("business-credential migration cannot run inside an existing transaction")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_opencompany_unit_credential_scope "
        "ON opencompany_business_units(business_id,credential_scope_id)"
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("""
            CREATE TABLE opencompany_business_credentials (
                business_id TEXT NOT NULL,
                credential_scope_id TEXT NOT NULL,
                credential_key TEXT NOT NULL,
                nonce BLOB NOT NULL,
                ciphertext BLOB NOT NULL,
                revision INTEGER NOT NULL CHECK(revision > 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(business_id,credential_key),
                UNIQUE(business_id,credential_scope_id,credential_key),
                FOREIGN KEY(business_id,credential_scope_id)
                    REFERENCES opencompany_business_units(business_id,credential_scope_id)
            )
        """)
        connection.execute("""
            CREATE INDEX idx_opencompany_business_credentials_scope
            ON opencompany_business_credentials(business_id,credential_scope_id,credential_key)
        """)
        connection.execute("""
            CREATE TABLE opencompany_business_credential_events (
                event_id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                credential_scope_id TEXT NOT NULL,
                credential_key TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('stored','rotated','deleted')),
                revision INTEGER NOT NULL CHECK(revision > 0),
                actor_type TEXT NOT NULL CHECK(actor_type='owner'),
                actor_id TEXT,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(business_id,credential_scope_id)
                    REFERENCES opencompany_business_units(business_id,credential_scope_id)
            )
        """)
        connection.execute("""
            CREATE INDEX idx_opencompany_business_credential_events_scope
            ON opencompany_business_credential_events(business_id,credential_key,occurred_at,event_id)
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_credential_events_no_update
            BEFORE UPDATE ON opencompany_business_credential_events
            BEGIN SELECT RAISE(ABORT, 'credential history is append-only'); END
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_credential_events_no_delete
            BEFORE DELETE ON opencompany_business_credential_events
            BEGIN SELECT RAISE(ABORT, 'credential history is append-only'); END
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_units_credential_scope_no_update
            BEFORE UPDATE OF credential_scope_id ON opencompany_business_units
            BEGIN SELECT RAISE(ABORT, 'business-unit credential scope is immutable'); END
        """)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("business-credential migration produced foreign-key violations")
        connection.execute("PRAGMA user_version = 11")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign-key enforcement is disabled after business-credential migration")



def _migrate_v11_business_integrations(connection: sqlite3.Connection) -> None:
    """Create an isolated integration registry without enabling external execution."""
    if connection.in_transaction:
        raise RuntimeError("business-integration migration cannot run inside an existing transaction")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_opencompany_unit_integration_scope "
            "ON opencompany_business_units(business_id,integration_scope_id)"
        )
        connection.execute("""
            CREATE TABLE opencompany_business_integrations (
                integration_id TEXT PRIMARY KEY,
                business_id TEXT NOT NULL,
                integration_scope_id TEXT NOT NULL,
                provider_key TEXT NOT NULL CHECK(length(provider_key) BETWEEN 2 AND 80),
                display_name TEXT NOT NULL CHECK(length(trim(display_name)) BETWEEN 1 AND 160),
                credential_scope_id TEXT NOT NULL,
                credential_key TEXT NOT NULL,
                permissions_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_review'
                    CHECK(status='pending_review'),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(integration_id,business_id,integration_scope_id),
                UNIQUE(business_id,provider_key),
                FOREIGN KEY(business_id,integration_scope_id)
                    REFERENCES opencompany_business_units(business_id,integration_scope_id),
                FOREIGN KEY(business_id,credential_scope_id)
                    REFERENCES opencompany_business_units(business_id,credential_scope_id)
            )
        """)
        connection.execute("""
            CREATE INDEX idx_opencompany_business_integrations_scope
            ON opencompany_business_integrations(business_id,integration_scope_id,status,created_at)
        """)
        connection.execute("""
            CREATE TABLE opencompany_business_integration_events (
                event_id TEXT PRIMARY KEY,
                integration_id TEXT NOT NULL,
                business_id TEXT NOT NULL,
                integration_scope_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('registered','paused','revoked')),
                actor_type TEXT NOT NULL CHECK(actor_type='owner'),
                actor_id TEXT,
                rationale TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(business_id,integration_scope_id)
                    REFERENCES opencompany_business_units(business_id,integration_scope_id),
                FOREIGN KEY(integration_id,business_id,integration_scope_id)
                    REFERENCES opencompany_business_integrations(integration_id,business_id,integration_scope_id)
            )
        """)
        connection.execute("""
            CREATE INDEX idx_opencompany_business_integration_events_scope
            ON opencompany_business_integration_events(business_id,integration_id,occurred_at,event_id)
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_integration_events_no_update
            BEFORE UPDATE ON opencompany_business_integration_events
            BEGIN SELECT RAISE(ABORT, 'integration history is append-only'); END
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_integration_events_no_delete
            BEFORE DELETE ON opencompany_business_integration_events
            BEGIN SELECT RAISE(ABORT, 'integration history is append-only'); END
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_integrations_no_scope_change
            BEFORE UPDATE OF business_id,integration_scope_id,provider_key,credential_key
            ON opencompany_business_integrations
            BEGIN SELECT RAISE(ABORT, 'integration identity and scope are immutable'); END
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_integrations_no_update
            BEFORE UPDATE ON opencompany_business_integrations
            BEGIN SELECT RAISE(ABORT, 'integration declarations are immutable'); END
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_integrations_no_delete
            BEFORE DELETE ON opencompany_business_integrations
            BEGIN SELECT RAISE(ABORT, 'integration declarations are immutable'); END
        """)
        connection.execute("""
            CREATE TRIGGER opencompany_business_units_integration_scope_no_update
            BEFORE UPDATE OF integration_scope_id ON opencompany_business_units
            BEGIN SELECT RAISE(ABORT, 'business-unit integration scope is immutable'); END
        """)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("business-integration migration produced foreign-key violations")
        connection.execute("PRAGMA user_version = 12")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign-key enforcement is disabled after business-integration migration")


def _migrate_v12_business_memory(connection: sqlite3.Connection) -> None:
    """Create append-only business memory versions under immutable memory scopes."""
    if connection.in_transaction:
        raise RuntimeError("business-memory migration cannot run inside an existing transaction")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_opencompany_unit_memory_scope ON opencompany_business_units(business_id,memory_scope_id)")
        connection.execute("""CREATE TABLE opencompany_business_memory_versions (
            memory_id TEXT NOT NULL,business_id TEXT NOT NULL,memory_scope_id TEXT NOT NULL,
            memory_key TEXT NOT NULL CHECK(length(memory_key) BETWEEN 1 AND 80),
            category TEXT NOT NULL CHECK(length(category) BETWEEN 2 AND 40),
            content TEXT NOT NULL CHECK(length(content)<=20000),
            source TEXT NOT NULL CHECK(length(source) BETWEEN 1 AND 500),
            revision INTEGER NOT NULL CHECK(revision>=1),
            operation TEXT NOT NULL CHECK(operation IN ('upsert','tombstone')),
            actor_type TEXT NOT NULL CHECK(actor_type='owner'),actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
            PRIMARY KEY(business_id,memory_scope_id,memory_key,revision),
            UNIQUE(memory_id,business_id,memory_scope_id,revision),
            FOREIGN KEY(business_id,memory_scope_id) REFERENCES opencompany_business_units(business_id,memory_scope_id)
        )""")
        connection.execute("CREATE INDEX idx_opencompany_business_memory_latest ON opencompany_business_memory_versions(business_id,memory_scope_id,memory_key,revision DESC)")
        connection.execute("""CREATE TRIGGER opencompany_business_memory_no_update BEFORE UPDATE ON opencompany_business_memory_versions
            BEGIN SELECT RAISE(ABORT,'business memory history is append-only'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_memory_no_delete BEFORE DELETE ON opencompany_business_memory_versions
            BEGIN SELECT RAISE(ABORT,'business memory history is append-only'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_units_memory_scope_no_update BEFORE UPDATE OF memory_scope_id ON opencompany_business_units
            BEGIN SELECT RAISE(ABORT,'business-unit memory scope is immutable'); END""")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("business-memory migration produced foreign-key violations")
        connection.execute("PRAGMA user_version=13")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction: connection.execute("ROLLBACK")
        raise


def _migrate_v13_business_assets(connection: sqlite3.Connection) -> None:
    """Create a metadata-only asset registry bound to immutable business asset scopes."""
    if connection.in_transaction:
        raise RuntimeError("business-asset migration cannot run inside an existing transaction")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_opencompany_unit_asset_scope ON opencompany_business_units(business_id,asset_scope_id)")
        connection.execute("""CREATE TABLE opencompany_business_assets (
            asset_id TEXT NOT NULL,
            business_id TEXT NOT NULL,
            asset_scope_id TEXT NOT NULL,
            asset_key TEXT NOT NULL CHECK(length(asset_key) BETWEEN 1 AND 80),
            title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
            asset_type TEXT NOT NULL CHECK(length(asset_type) BETWEEN 2 AND 40),
            filename TEXT NOT NULL CHECK(length(filename) BETWEEN 1 AND 255),
            media_type TEXT NOT NULL CHECK(length(media_type) BETWEEN 3 AND 120),
            checksum_sha256 TEXT NOT NULL CHECK(length(checksum_sha256)=64),
            byte_size INTEGER NOT NULL CHECK(byte_size BETWEEN 0 AND 104857600),
            source TEXT NOT NULL CHECK(length(source) BETWEEN 1 AND 500),
            storage_state TEXT NOT NULL CHECK(storage_state='metadata_only'),
            status TEXT NOT NULL CHECK(status='pending_storage'),
            actor_type TEXT NOT NULL CHECK(actor_type='owner'),
            actor_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(business_id,asset_scope_id,asset_key),
            UNIQUE(asset_id,business_id,asset_scope_id),
            FOREIGN KEY(business_id,asset_scope_id)
                REFERENCES opencompany_business_units(business_id,asset_scope_id)
        )""")
        connection.execute("""CREATE TABLE opencompany_business_asset_events (
            event_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            business_id TEXT NOT NULL,
            asset_scope_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('declared')),
            actor_type TEXT NOT NULL CHECK(actor_type='owner'),
            actor_id TEXT NOT NULL,
            details_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            FOREIGN KEY(asset_id,business_id,asset_scope_id)
                REFERENCES opencompany_business_assets(asset_id,business_id,asset_scope_id)
        )""")
        connection.execute("CREATE INDEX idx_opencompany_business_assets_scope ON opencompany_business_assets(business_id,asset_scope_id,created_at DESC)")
        connection.execute("CREATE INDEX idx_opencompany_business_asset_events_history ON opencompany_business_asset_events(business_id,asset_scope_id,asset_id,occurred_at)")
        connection.execute("""CREATE TRIGGER opencompany_business_assets_no_update BEFORE UPDATE ON opencompany_business_assets
            BEGIN SELECT RAISE(ABORT,'business asset declarations are immutable'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_assets_no_delete BEFORE DELETE ON opencompany_business_assets
            BEGIN SELECT RAISE(ABORT,'business asset declarations are immutable'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_asset_events_no_update BEFORE UPDATE ON opencompany_business_asset_events
            BEGIN SELECT RAISE(ABORT,'business asset events are append-only'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_asset_events_no_delete BEFORE DELETE ON opencompany_business_asset_events
            BEGIN SELECT RAISE(ABORT,'business asset events are append-only'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_units_asset_scope_no_update BEFORE UPDATE OF asset_scope_id ON opencompany_business_units
            BEGIN SELECT RAISE(ABORT,'business-unit asset scope is immutable'); END""")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("business-asset migration produced foreign-key violations")
        connection.execute("PRAGMA user_version=14")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise



def _migrate_v14_business_asset_storage(connection: sqlite3.Connection) -> None:
    """Record verified private storage as append-only business-scoped lifecycle events."""
    if connection.in_transaction:
        raise RuntimeError("business-asset storage migration cannot run inside an existing transaction")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("""CREATE TABLE opencompany_business_asset_storage_events (
            event_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            business_id TEXT NOT NULL,
            asset_scope_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action='stored_unscanned'),
            storage_key TEXT NOT NULL UNIQUE CHECK(length(storage_key) BETWEEN 1 AND 160),
            checksum_sha256 TEXT NOT NULL CHECK(length(checksum_sha256)=64),
            byte_size INTEGER NOT NULL CHECK(byte_size BETWEEN 0 AND 104857600),
            actor_type TEXT NOT NULL CHECK(actor_type='owner'),
            actor_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            UNIQUE(business_id,asset_scope_id,asset_id),
            FOREIGN KEY(asset_id,business_id,asset_scope_id)
                REFERENCES opencompany_business_assets(asset_id,business_id,asset_scope_id)
        )""")
        connection.execute("""CREATE INDEX idx_opencompany_asset_storage_scope
            ON opencompany_business_asset_storage_events(business_id,asset_scope_id,occurred_at)""")
        connection.execute("""CREATE TRIGGER opencompany_business_asset_storage_events_no_update
            BEFORE UPDATE ON opencompany_business_asset_storage_events
            BEGIN SELECT RAISE(ABORT,'asset storage lifecycle history is append-only'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_asset_storage_events_no_delete
            BEFORE DELETE ON opencompany_business_asset_storage_events
            BEGIN SELECT RAISE(ABORT,'asset storage lifecycle history is append-only'); END""")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("business-asset storage migration produced foreign-key violations")
        connection.execute("PRAGMA user_version=15")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise



def _migrate_v15_business_asset_scans(connection: sqlite3.Connection) -> None:
    """Store immutable malware-scan verdicts linked to an actually stored asset."""
    if connection.in_transaction:
        raise RuntimeError("business-asset scan migration cannot run inside an existing transaction")
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("""CREATE TABLE opencompany_business_asset_scan_events (
            event_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            business_id TEXT NOT NULL,
            asset_scope_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('scan_clean','scan_infected')),
            scanner_key TEXT NOT NULL CHECK(scanner_key='clamav-unix-socket'),
            checksum_sha256 TEXT NOT NULL CHECK(length(checksum_sha256)=64),
            byte_size INTEGER NOT NULL CHECK(byte_size BETWEEN 0 AND 104857600),
            verdict TEXT NOT NULL CHECK(length(verdict) BETWEEN 1 AND 500),
            actor_type TEXT NOT NULL CHECK(actor_type='scanner'),
            actor_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            FOREIGN KEY(business_id,asset_scope_id,asset_id)
                REFERENCES opencompany_business_asset_storage_events(business_id,asset_scope_id,asset_id)
        )""")
        connection.execute("""CREATE INDEX idx_opencompany_asset_scan_scope
            ON opencompany_business_asset_scan_events(business_id,asset_scope_id,asset_id,occurred_at)""")
        connection.execute("""CREATE TRIGGER opencompany_business_asset_scan_events_no_update
            BEFORE UPDATE ON opencompany_business_asset_scan_events
            BEGIN SELECT RAISE(ABORT,'asset scan history is append-only'); END""")
        connection.execute("""CREATE TRIGGER opencompany_business_asset_scan_events_no_delete
            BEFORE DELETE ON opencompany_business_asset_scan_events
            BEGIN SELECT RAISE(ABORT,'asset scan history is append-only'); END""")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("business-asset scan migration produced foreign-key violations")
        connection.execute("PRAGMA user_version=16")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _audit_payload(record: AuditRecord, previous_hash: str) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "occurred_at": record.occurred_at.isoformat(),
        "actor_type": record.actor_type,
        "actor_id": record.actor_id,
        "action": record.action,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "outcome": record.outcome,
        "correlation_id": record.correlation_id,
        "details": dict(record.details),
        "previous_hash": previous_hash,
    }


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


class SQLiteStore:
    """Thread-safe repository for core records and append-only audit evidence."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        if self.database != ":memory:":
            parent = Path(self.database).expanduser().resolve().parent
            if not parent.exists():
                raise FileNotFoundError(f"database directory does not exist: {parent}")
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.database, timeout=10, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 10000")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise RuntimeError("database schema is newer than this application supports")
            if version == _SCHEMA_VERSION:
                return
            if version == 0:
                self._connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS agent_profiles (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        department TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        capabilities_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        role_key TEXT,
                        team_key TEXT
                    );
                    CREATE TABLE IF NOT EXISTS work_items (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        objective TEXT NOT NULL,
                        department TEXT NOT NULL,
                        business_id TEXT NOT NULL DEFAULT 'core',
                        state TEXT NOT NULL,
                        assigned_agent_id TEXT,
                        dependencies_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS audit_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        occurred_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL UNIQUE
                    );
                    CREATE INDEX IF NOT EXISTS idx_work_items_state_created
                        ON work_items(state, created_at);
                    CREATE TABLE IF NOT EXISTS deliverables (id TEXT PRIMARY KEY, work_item_id TEXT NOT NULL REFERENCES work_items(id), role_key TEXT NOT NULL, content TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, cost_usd REAL NOT NULL CHECK(cost_usd >= 0), created_at TEXT NOT NULL, review_required INTEGER NOT NULL CHECK(review_required IN (0,1)));
                    CREATE INDEX IF NOT EXISTS idx_deliverables_work_item ON deliverables(work_item_id, created_at);
                    PRAGMA user_version = 4;
                    COMMIT;
                """)
                version = 4
            if version == 1:
                columns = {
                    row["name"] for row in self._connection.execute(
                        "PRAGMA table_info(agent_profiles)"
                    ).fetchall()
                }
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    if "role_key" not in columns:
                        self._connection.execute("ALTER TABLE agent_profiles ADD COLUMN role_key TEXT")
                    if "team_key" not in columns:
                        self._connection.execute("ALTER TABLE agent_profiles ADD COLUMN team_key TEXT")
                    self._connection.execute("PRAGMA user_version = 2")
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
                version = 2
            if version == 2:
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    self._connection.execute("CREATE TABLE IF NOT EXISTS deliverables (id TEXT PRIMARY KEY, work_item_id TEXT NOT NULL REFERENCES work_items(id), role_key TEXT NOT NULL, content TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, cost_usd REAL NOT NULL CHECK(cost_usd >= 0), created_at TEXT NOT NULL, review_required INTEGER NOT NULL CHECK(review_required IN (0,1)))")
                    self._connection.execute("CREATE INDEX IF NOT EXISTS idx_deliverables_work_item ON deliverables(work_item_id, created_at)")
                    self._connection.execute("PRAGMA user_version = 3")
                    self._connection.execute("COMMIT")
                    version = 3
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
            if version == 3:
                columns = {
                    row["name"] for row in self._connection.execute(
                        "PRAGMA table_info(work_items)"
                    ).fetchall()
                }
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    if "business_id" not in columns:
                        self._connection.execute(
                            "ALTER TABLE work_items ADD COLUMN business_id TEXT NOT NULL DEFAULT 'core'"
                        )
                    self._connection.execute("PRAGMA user_version = 4")
                    self._connection.execute("COMMIT")
                    version = 4
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
            if version == 4:
                try:
                    self._connection.executescript("""
                        BEGIN IMMEDIATE;
                        CREATE TABLE IF NOT EXISTS commercial_opportunities (
                            id TEXT PRIMARY KEY,
                            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
                            customer_name TEXT NOT NULL,
                            customer_contact TEXT,
                            customer_need TEXT NOT NULL,
                            stage TEXT NOT NULL DEFAULT 'new' CHECK(stage IN ('new','qualified','proposal','won','lost','on_hold')),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_opportunities_unit
                            ON commercial_opportunities(business_id, created_at);
                        CREATE TABLE IF NOT EXISTS commercial_products (
                            id TEXT PRIMARY KEY,
                            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
                            name TEXT NOT NULL,
                            description TEXT NOT NULL,
                            category TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','archived')),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_products_unit
                            ON commercial_products(business_id, status, created_at);
                        PRAGMA user_version = 5;
                        COMMIT;
                    """)
                    version = 5
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
            if version == 5:
                try:
                    self._connection.executescript("""
                        BEGIN IMMEDIATE;
                        CREATE TABLE IF NOT EXISTS commercial_quotes (
                            id TEXT PRIMARY KEY,
                            opportunity_id TEXT NOT NULL REFERENCES commercial_opportunities(id),
                            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
                            title TEXT NOT NULL,
                            currency TEXT NOT NULL CHECK(length(currency)=3),
                            currency_exponent INTEGER NOT NULL CHECK(currency_exponent BETWEEN 0 AND 3),
                            subtotal_minor INTEGER NOT NULL CHECK(subtotal_minor > 0),
                            terms TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved_for_delivery','accepted','rejected','void')),
                            acceptance_reference TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_quotes_scope
                            ON commercial_quotes(business_id, opportunity_id, created_at);
                        CREATE TABLE IF NOT EXISTS commercial_quote_items (
                            id TEXT PRIMARY KEY,
                            quote_id TEXT NOT NULL REFERENCES commercial_quotes(id) ON DELETE CASCADE,
                            product_id TEXT NOT NULL REFERENCES commercial_products(id),
                            description TEXT NOT NULL,
                            quantity INTEGER NOT NULL CHECK(quantity > 0),
                            unit_price_minor INTEGER NOT NULL CHECK(unit_price_minor > 0),
                            line_total_minor INTEGER NOT NULL CHECK(line_total_minor > 0)
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_quote_items_quote
                            ON commercial_quote_items(quote_id);
                        CREATE TABLE IF NOT EXISTS commercial_orders (
                            id TEXT PRIMARY KEY,
                            quote_id TEXT NOT NULL UNIQUE REFERENCES commercial_quotes(id),
                            opportunity_id TEXT NOT NULL REFERENCES commercial_opportunities(id),
                            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
                            customer_name TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'awaiting_owner_fulfilment' CHECK(status IN ('awaiting_owner_fulfilment','in_progress','fulfilled','cancelled')),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_orders_scope
                            ON commercial_orders(business_id, status, created_at);
                        PRAGMA user_version = 6;
                        COMMIT;
                    """)
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
                version = 6
            if version == 6:
                try:
                    self._connection.executescript("""
                        BEGIN IMMEDIATE;
                        CREATE TABLE IF NOT EXISTS commercial_suppliers (
                            id TEXT PRIMARY KEY,
                            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand')),
                            relationship_type TEXT NOT NULL CHECK(relationship_type IN ('agency_supplier','own_brand_supplier')),
                            name TEXT NOT NULL,
                            contact_name TEXT,
                            email TEXT,
                            phone TEXT,
                            country TEXT,
                            product_categories_json TEXT NOT NULL,
                            verification_status TEXT NOT NULL DEFAULT 'draft' CHECK(verification_status IN ('draft','verified','blocked')),
                            notes TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            CHECK((business_id='physical-agency' AND relationship_type='agency_supplier')
                               OR (business_id='physical-brand' AND relationship_type='own_brand_supplier'))
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_suppliers_scope
                            ON commercial_suppliers(business_id, verification_status, created_at);
                        PRAGMA user_version = 7;
                        COMMIT;
                    """)
                    version = 7
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
                version = 7
            if version == 7:
                _migrate_v7_commercial_business_ids(self._connection)
                version = 8
            if version == 8:
                _migrate_v8_customer_scopes(self._connection)
                version = 9
            if version == 9:
                _migrate_v9_finance_ledger(self._connection)
                version = 10
            if version == 10:
                _migrate_v10_business_credentials(self._connection)
                version = 11
            if version == 11:
                _migrate_v11_business_integrations(self._connection)
                version = 12
            if version == 12:
                _migrate_v12_business_memory(self._connection)
                version = 13
            if version == 13:
                _migrate_v13_business_assets(self._connection)
                version = 14
            if version == 14:
                _migrate_v14_business_asset_storage(self._connection)
                version = 15
            if version == 15:
                _migrate_v15_business_asset_scans(self._connection)
                return
            raise RuntimeError(f"unsupported database schema version: {version}")


    def create_commercial_opportunity(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Create one customer opportunity scoped to exactly one commercial business."""
        _assert_operational_commercial_scope(self._connection, self._lock, record.get("business_id"))
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO commercial_opportunities
                       (id,business_id,customer_scope_id,customer_name,customer_contact,customer_need,stage,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (record["id"], record["business_id"], _assert_operational_commercial_scope(
                        self._connection, self._lock, record["business_id"]
                    )["customer_scope_id"], record["customer_name"], record.get("customer_contact"),
                     record["customer_need"], record.get("stage", "new"),
                     record["created_at"], record["updated_at"]),
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
        if business_id is not None:
            _assert_operational_commercial_scope(self._connection, self._lock, business_id)
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

    def create_commercial_product(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Create a draft catalogue entry inside exactly one commercial unit."""
        _assert_operational_commercial_scope(self._connection, self._lock, record.get("business_id"))
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO commercial_products
                       (id,business_id,name,description,category,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (record["id"], record["business_id"], record["name"],
                     record["description"], record["category"], record.get("status", "draft"),
                     record["created_at"], record["updated_at"]),
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

    def update_commercial_product_status(
        self, product_id: str, status: str, audit: AuditRecord
    ) -> bool:
        if status not in {"active", "archived"}:
            raise ValueError("catalogue status must be active or archived")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                product = self._connection.execute(
                    "SELECT business_id FROM commercial_products WHERE id=?", (product_id,)
                ).fetchone()
                if product is None:
                    self._connection.execute("ROLLBACK")
                    return False
                _assert_operational_commercial_scope(self._connection, self._lock, product["business_id"])
                cursor = self._connection.execute(
                    "UPDATE commercial_products SET status=?,updated_at=? WHERE id=? AND status!='archived'",
                    (status, datetime.now(timezone.utc).isoformat(), product_id),
                )
                if cursor.rowcount != 1:
                    self._connection.execute("ROLLBACK")
                    return False
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

    def list_commercial_products(
        self, *, business_id: str | None = None, status: str | None = None, limit: int = 500
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if business_id is not None:
            _assert_operational_commercial_scope(self._connection, self._lock, business_id)
        if status is not None and status not in {"draft", "active", "archived"}:
            raise ValueError("unknown catalogue status")
        clauses, values = [], []
        if business_id is not None:
            clauses.append("business_id=?")
            values.append(business_id)
        if status is not None:
            clauses.append("status=?")
            values.append(status)
        sql = "SELECT * FROM commercial_products"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
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
                _assert_operational_commercial_scope(self._connection, self._lock, business_id)
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
                       (id,opportunity_id,business_id,customer_scope_id,title,currency,currency_exponent,subtotal_minor,terms,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,'draft',?,?)""",
                    (record["id"], record["opportunity_id"], business_id,
                     opportunity["customer_scope_id"], record["title"], record["currency"],
                     record["currency_exponent"], subtotal, record["terms"],
                     record["created_at"], record["updated_at"]),
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
        if business_id is not None:
            _assert_operational_commercial_scope(self._connection, self._lock, business_id)
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
                    "SELECT status,business_id FROM commercial_quotes WHERE id=?", (quote_id,)
                ).fetchone()
                if quote is None:
                    self._connection.execute("ROLLBACK")
                    return False
                _assert_operational_commercial_scope(self._connection, self._lock, quote["business_id"])
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
                _assert_operational_commercial_scope(self._connection, self._lock, quote["business_id"])
                existing_order = self._connection.execute(
                    "SELECT id FROM commercial_orders WHERE quote_id=?", (quote_id,)
                ).fetchone()
                if existing_order is not None:
                    raise ValueError("an order already exists for this quote")
                self._connection.execute(
                    """INSERT INTO commercial_orders
                       (id,quote_id,opportunity_id,business_id,customer_scope_id,customer_name,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,'awaiting_owner_fulfilment',?,?)""",
                    (order_id, quote_id, quote["opportunity_id"], quote["business_id"],
                     quote["customer_scope_id"], quote["customer_name"],
                     datetime.now(timezone.utc).isoformat(),
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
                    "SELECT status,business_id FROM commercial_orders WHERE id=?", (order_id,)
                ).fetchone()
                if order is None:
                    self._connection.execute("ROLLBACK")
                    return False
                _assert_operational_commercial_scope(self._connection, self._lock, order["business_id"])
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
        if business_id is not None:
            _assert_operational_commercial_scope(self._connection, self._lock, business_id)
        sql = "SELECT * FROM commercial_orders"
        values: tuple[Any, ...] = ()
        if business_id is not None:
            sql += " WHERE business_id=?"
            values = (business_id,)
        sql += " ORDER BY created_at DESC,id"
        with self._lock:
            rows = self._connection.execute(sql, values).fetchall()
        return tuple(dict(row) for row in rows)


    def create_finance_entry(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Record an internal financial fact; this method never moves money."""
        business_id = record.get("business_id")
        unit = _assert_operational_commercial_scope(self._connection, self._lock, business_id)
        entry_type = record.get("entry_type")
        if entry_type not in {"revenue", "expense", "refund", "adjustment"}:
            raise ValueError("unsupported finance entry type")
        amount_minor = record.get("amount_minor")
        if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
            raise ValueError("amount_minor must be a positive integer in the currency's minor unit")
        currency = record.get("currency")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a three-letter uppercase ISO currency code")
        description = record.get("description")
        if not isinstance(description, str) or not description.strip() or len(description) > 2000:
            raise ValueError("description must contain 1-2000 characters")
        source_reference = record.get("source_reference")
        if source_reference is not None and (
            not isinstance(source_reference, str) or len(source_reference) > 300
        ):
            raise ValueError("source_reference must be at most 300 characters")
        entry_id = record.get("id")
        created_at = record.get("created_at")
        if not isinstance(entry_id, str) or not entry_id.strip() or len(entry_id) > 128:
            raise ValueError("finance entry id is required")
        if not isinstance(created_at, str) or not created_at.strip() or len(created_at) > 80:
            raise ValueError("created_at is required")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                # Re-resolve inside the transaction; callers cannot choose a finance scope.
                current_unit = _assert_operational_commercial_scope(
                    self._connection, self._lock, business_id
                )
                finance_scope_id = current_unit["finance_scope_id"]
                self._connection.execute(
                    """INSERT INTO opencompany_finance_entries
                       (id,business_id,finance_scope_id,entry_type,amount_minor,currency,
                        description,source_reference,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (entry_id, business_id, finance_scope_id, entry_type, amount_minor,
                     currency, description.strip(), source_reference, created_at),
                )
                event_id = str(uuid4())
                self._connection.execute(
                    """INSERT INTO opencompany_finance_entry_events
                       (event_id,entry_id,business_id,finance_scope_id,action,actor_type,
                        actor_id,rationale,occurred_at)
                       VALUES(?,?,?,?, 'recorded',?,?,?,?)""",
                    (event_id, entry_id, business_id, finance_scope_id,
                     "owner" if audit.actor_type == "owner" else "system", audit.actor_id,
                     "Internal record created; no payment or transfer was initiated.",
                     audit.occurred_at.isoformat()),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                details = dict(audit.details)
                details.update({"business_id": business_id, "finance_entry_id": entry_id,
                                "entry_type": entry_type, "amount_minor": amount_minor,
                                "currency": currency, "description": description.strip(),
                                "source_reference": source_reference})
                audited = AuditRecord(
                    id=audit.id, occurred_at=audit.occurred_at, actor_type=audit.actor_type,
                    actor_id=audit.actor_id, action=audit.action, subject_type="finance_entry",
                    subject_id=entry_id, outcome=audit.outcome, correlation_id=audit.correlation_id,
                    details=details,
                )
                payload = _audit_payload(audited, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(audited.id), audited.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise


    def append_finance_review_event(
        self, entry_id: str, action: str, rationale: str, audit: AuditRecord
    ) -> bool:
        """Append a decision from the owner-authenticated service boundary; never executes payment."""
        if audit.actor_type != "owner":
            raise PermissionError("finance review decisions require the owner actor marker from the authenticated API boundary")
        if action not in {"owner_verified", "owner_rejected", "owner_approved"}:
            raise ValueError("unsupported owner finance review action")
        if not isinstance(rationale, str) or len(rationale) > 2000:
            raise ValueError("rationale must be at most 2000 characters")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                entry = self._connection.execute(
                    "SELECT id,business_id,finance_scope_id FROM opencompany_finance_entries WHERE id=?",
                    (entry_id,),
                ).fetchone()
                if entry is None:
                    self._connection.execute("ROLLBACK")
                    return False
                _assert_operational_commercial_scope(
                    self._connection, self._lock, entry["business_id"]
                )
                prior_decision = self._connection.execute(
                    """SELECT action FROM opencompany_finance_entry_events
                       WHERE entry_id=? AND action!='recorded'
                       ORDER BY occurred_at DESC,event_id DESC LIMIT 1""",
                    (entry_id,),
                ).fetchone()
                if prior_decision is not None:
                    raise ValueError("finance entry already has an owner review decision")
                self._connection.execute(
                    """INSERT INTO opencompany_finance_entry_events
                       (event_id,entry_id,business_id,finance_scope_id,action,actor_type,
                        actor_id,rationale,occurred_at)
                       VALUES(?,?,?,?,?,'owner',?,?,?)""",
                    (str(uuid4()), entry_id, entry["business_id"], entry["finance_scope_id"],
                     action, audit.actor_id, rationale.strip(), audit.occurred_at.isoformat()),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                details = dict(audit.details)
                details.update({"business_id": entry["business_id"], "finance_entry_id": entry_id,
                                "finance_decision": action, "rationale": rationale.strip()})
                audited = AuditRecord(
                    id=audit.id, occurred_at=audit.occurred_at, actor_type="owner",
                    actor_id=audit.actor_id, action=audit.action, subject_type="finance_entry",
                    subject_id=entry_id, outcome=action, correlation_id=audit.correlation_id,
                    details=details,
                )
                payload = _audit_payload(audited, previous_hash)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(audited.id), audited.occurred_at.isoformat(), _json(payload),
                     previous_hash, _digest(payload)),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def list_finance_entries(
        self, *, business_id: str | None = None, limit: int = 500
    ) -> tuple[dict[str, Any], ...]:
        """List only entries in the requested operational business scope."""
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        sql = """SELECT e.*, (
                    SELECT v.action FROM opencompany_finance_entry_events v
                    WHERE v.entry_id=e.id ORDER BY v.occurred_at DESC,v.event_id DESC LIMIT 1
                 ) AS latest_review_action
                 FROM opencompany_finance_entries e"""
        values: list[Any] = []
        if business_id is not None:
            _assert_operational_commercial_scope(self._connection, self._lock, business_id)
            sql += " WHERE e.business_id=?"
            values.append(business_id)
        sql += " ORDER BY e.created_at DESC,e.id LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(sql, tuple(values)).fetchall()
        return tuple(dict(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def save_agent(self, agent: AgentProfile) -> None:
        with self._lock:
            self._connection.execute(
                """INSERT INTO agent_profiles
                   (id,name,department,purpose,capabilities_json,state,revision,role_key,team_key)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, department=excluded.department,
                     purpose=excluded.purpose, capabilities_json=excluded.capabilities_json,
                     state=excluded.state, revision=excluded.revision,
                     role_key=excluded.role_key, team_key=excluded.team_key""",
                (str(agent.id), agent.name, agent.department, agent.purpose,
                 _json(list(agent.capabilities)), agent.state.value, agent.revision,
                 agent.role_key, agent.team_key),
            )

    def list_agents(self, *, department: str | None = None, limit: int = 100) -> tuple[AgentProfile, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._lock:
            if department is None:
                rows = self._connection.execute(
                    "SELECT id FROM agent_profiles ORDER BY department,name,id LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT id FROM agent_profiles WHERE department=? ORDER BY name,id LIMIT ?",
                    (department, limit),
                ).fetchall()
        return tuple(self.get_agent(UUID(row["id"])) for row in rows)

    def save_agent_with_audit(self, agent: AgentProfile, record: AuditRecord) -> str | None:
        """Insert a new agent profile and its audit evidence atomically.

        Existing profiles are never overwritten by bootstrap retries.
        """
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    """INSERT OR IGNORE INTO agent_profiles
                       (id,name,department,purpose,capabilities_json,state,revision,role_key,team_key)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (str(agent.id), agent.name, agent.department, agent.purpose,
                     _json(list(agent.capabilities)), agent.state.value, agent.revision,
                     agent.role_key, agent.team_key),
                )
                if cursor.rowcount == 0:
                    self._connection.execute("ROLLBACK")
                    return None
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def update_agent_with_audit(
        self, agent: AgentProfile, record: AuditRecord, *, expected_revision: int
    ) -> bool:
        """Update an existing agent and append its audit event atomically."""
        if agent.revision != expected_revision + 1:
            raise ValueError("updated agent revision must increment exactly once")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    """UPDATE agent_profiles SET name=?,department=?,purpose=?,
                       capabilities_json=?,state=?,revision=?,role_key=?,team_key=?
                       WHERE id=? AND revision=?""",
                    (agent.name, agent.department, agent.purpose,
                     _json(list(agent.capabilities)), agent.state.value, agent.revision,
                     agent.role_key, agent.team_key, str(agent.id), expected_revision),
                )
                if cursor.rowcount != 1:
                    self._connection.execute("ROLLBACK")
                    return False
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def activate_all_draft_agents_with_audit(self) -> int:
        """Atomically activate all provisioned, catalogue-bound draft profiles."""
        correlation_id = str(uuid4())
        now = datetime.now(timezone.utc)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                rows = self._connection.execute(
                    """SELECT id,department,role_key,team_key,revision
                       FROM agent_profiles WHERE state=? ORDER BY department,role_key,id""",
                    (AgentState.DRAFT.value,),
                ).fetchall()
                for row in rows:
                    if not row["department"] or not row["role_key"] or not row["team_key"]:
                        raise ValueError("cannot activate a profile without department, role and team identity")
                    cursor = self._connection.execute(
                        """UPDATE agent_profiles SET state=?,revision=revision+1
                           WHERE id=? AND state=? AND revision=?""",
                        (AgentState.ACTIVE.value, row["id"], AgentState.DRAFT.value, row["revision"]),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("draft profile changed during workforce activation")
                    event = AuditRecord(
                        id=uuid4(), occurred_at=now, actor_type="owner",
                        actor_id="owner", action="agent.workforce_profile_activated",
                        subject_type="agent_profile", subject_id=row["id"],
                        outcome="active", correlation_id=correlation_id,
                        details={
                            "department": row["department"], "role_key": row["role_key"],
                            "team_key": row["team_key"], "activation_policy": "owner-approved-runtime-config",
                        },
                    )
                    previous = self._connection.execute(
                        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                    payload = _audit_payload(event, previous_hash)
                    self._connection.execute(
                        """INSERT INTO audit_events
                           (event_id,occurred_at,payload_json,previous_hash,event_hash)
                           VALUES(?,?,?,?,?)""",
                        (str(event.id), event.occurred_at.isoformat(), _json(payload),
                         previous_hash, _digest(payload)),
                    )
                self._connection.execute("COMMIT")
                return len(rows)
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def get_agent(self, agent_id: UUID) -> AgentProfile | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM agent_profiles WHERE id=?", (str(agent_id),)
            ).fetchone()
        if row is None:
            return None
        return AgentProfile(
            id=UUID(row["id"]), name=row["name"], department=row["department"],
            purpose=row["purpose"], capabilities=tuple(json.loads(row["capabilities_json"])),
            state=AgentState(row["state"]), revision=row["revision"],
            role_key=row["role_key"], team_key=row["team_key"],
        )

    def save_work_item(self, item: WorkItem) -> None:
        _assert_operational_work_item_scope(self._connection, self._lock, item.business_id)
        with self._lock:
            existing = self._connection.execute(
                "SELECT business_id FROM work_items WHERE id=?", (str(item.id),)
            ).fetchone()
            if existing is not None and existing["business_id"] != item.business_id:
                raise ValueError("a work item's business unit is immutable")
            self._connection.execute(
                """INSERT INTO work_items
                   (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, objective=excluded.objective,
                     department=excluded.department, state=excluded.state,
                     assigned_agent_id=excluded.assigned_agent_id,
                     dependencies_json=excluded.dependencies_json,
                     created_at=excluded.created_at""",
                (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                 str(item.assigned_agent_id) if item.assigned_agent_id else None,
                 _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
            )

    def save_work_item_with_audit(self, item: WorkItem, record: AuditRecord) -> str:
        _assert_operational_work_item_scope(self._connection, self._lock, item.business_id)
        """Persist a work item change and its audit evidence in one transaction."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT business_id FROM work_items WHERE id=?", (str(item.id),)
                ).fetchone()
                if existing is not None and existing["business_id"] != item.business_id:
                    raise ValueError("a work item's business unit is immutable")
                self._connection.execute(
                    """INSERT INTO work_items
                       (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         title=excluded.title, objective=excluded.objective,
                         department=excluded.department, state=excluded.state,
                         assigned_agent_id=excluded.assigned_agent_id,
                         dependencies_json=excluded.dependencies_json,
                         created_at=excluded.created_at""",
                    (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                     str(item.assigned_agent_id) if item.assigned_agent_id else None,
                     _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                )
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def save_work_items_with_audit(
        self, items: tuple[WorkItem, ...], records: tuple[AuditRecord, ...]
    ) -> None:
        """Persist a complete draft plan and all audit events atomically."""
        if not items or len(items) != len(records):
            raise ValueError("each planned work item requires one audit record")
        for item in items:
            _assert_operational_work_item_scope(self._connection, self._lock, item.business_id)
        if len({item.id for item in items}) != len(items):
            raise ValueError("planned work item identifiers must be unique")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    self._connection.execute(
                        """INSERT INTO work_items
                           (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (str(item.id), item.title, item.objective, item.department, item.business_id,
                         item.state.value, str(item.assigned_agent_id) if item.assigned_agent_id else None,
                         _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                    )
                for record in records:
                    row = self._connection.execute(
                        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    previous_hash = row["event_hash"] if row else _ZERO_HASH
                    payload = _audit_payload(record, previous_hash)
                    self._connection.execute(
                        """INSERT INTO audit_events
                           (event_id,occurred_at,payload_json,previous_hash,event_hash)
                           VALUES(?,?,?,?,?)""",
                        (str(record.id), record.occurred_at.isoformat(), _json(payload),
                         previous_hash, _digest(payload)),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def approve_delegation_proposal(
        self, proposal_id: UUID, items: tuple[WorkItem, ...],
        records: tuple[AuditRecord, ...], *, parent_update: WorkItem | None = None,
    ) -> bool:
        """Atomically approve a draft proposal, materialize child tasks, and audit."""
        if not items or not records:
            raise ValueError("approved delegation requires child tasks and audit records")
        for item in items:
            _assert_operational_work_item_scope(self._connection, self._lock, item.business_id)
        if parent_update is not None:
            _assert_operational_work_item_scope(self._connection, self._lock, parent_update.business_id)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                proposal = self._connection.execute(
                    "SELECT status FROM delegation_proposals WHERE id=?",
                    (str(proposal_id),),
                ).fetchone()
                if proposal is None or proposal["status"] != "draft":
                    self._connection.execute("ROLLBACK")
                    return False
                expected_ids = {
                    row["id"] for row in self._connection.execute(
                        "SELECT id FROM delegation_child_tasks WHERE proposal_id=? AND state='draft'",
                        (str(proposal_id),),
                    ).fetchall()
                }
                if expected_ids != {str(item.id) for item in items}:
                    self._connection.execute("ROLLBACK")
                    raise ValueError("materialized tasks do not match the proposal's draft children")
                if parent_update is not None:
                    parent_row = self._connection.execute(
                        "SELECT state,assigned_agent_id,department,business_id FROM work_items WHERE id=?",
                        (str(parent_update.id),),
                    ).fetchone()
                    if (
                        parent_row is None
                        or parent_row["state"] != TaskState.DRAFT.value
                        or parent_row["assigned_agent_id"] is not None
                        or parent_row["department"] != parent_update.department
                        or parent_row["business_id"] != parent_update.business_id
                        or any(item.business_id != parent_update.business_id for item in items)
                        or parent_update.state != TaskState.READY
                        or parent_update.assigned_agent_id is None
                        or set(parent_update.depends_on) != {item.id for item in items}
                    ):
                        self._connection.execute("ROLLBACK")
                        raise ValueError("manager synthesis parent must be an unassigned DRAFT task depending on every approved child")
                    changed = self._connection.execute(
                        """UPDATE work_items SET state=?,assigned_agent_id=?,dependencies_json=?
                           WHERE id=? AND state=? AND assigned_agent_id IS NULL""",
                        (parent_update.state.value, str(parent_update.assigned_agent_id),
                         _json([str(value) for value in parent_update.depends_on]),
                         str(parent_update.id), TaskState.DRAFT.value),
                    )
                    if changed.rowcount != 1:
                        self._connection.execute("ROLLBACK")
                        return False
                for item in items:
                    self._connection.execute(
                        """INSERT INTO work_items
                           (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                         str(item.assigned_agent_id) if item.assigned_agent_id else None,
                         _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                    )
                for record in records:
                    row = self._connection.execute(
                        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    previous_hash = row["event_hash"] if row else _ZERO_HASH
                    payload = _audit_payload(record, previous_hash)
                    event_hash = _digest(payload)
                    self._connection.execute(
                        """INSERT INTO audit_events
                           (event_id,occurred_at,payload_json,previous_hash,event_hash)
                           VALUES(?,?,?,?,?)""",
                        (str(record.id), record.occurred_at.isoformat(), _json(payload),
                         previous_hash, event_hash),
                    )
                self._connection.execute(
                    "UPDATE delegation_child_tasks SET state='approved' WHERE proposal_id=? AND state='draft'",
                    (str(proposal_id),),
                )
                self._connection.execute(
                    "UPDATE delegation_proposals SET status='approved' WHERE id=? AND status='draft'",
                    (str(proposal_id),),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def save(self, deliverable: Any) -> None:
        """Idempotently stage a review-required artifact before its atomic audit transition."""
        if not deliverable.review_required:
            raise ValueError("worker deliverables must require review")
        values = (
            str(deliverable.work_item_id), deliverable.role_key, deliverable.content,
            deliverable.provider, deliverable.model, float(deliverable.cost_usd),
            deliverable.created_at.isoformat(), 1,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute(
                    "SELECT state FROM work_items WHERE id=?", (str(deliverable.work_item_id),)
                ).fetchone()
                if item is None or item["state"] != TaskState.IN_PROGRESS.value:
                    raise ValueError("artifact can only be staged for an in-progress work item")
                existing = self._connection.execute(
                    "SELECT * FROM deliverables WHERE id=?", (str(deliverable.id),)
                ).fetchone()
                if existing is not None:
                    old = (
                        existing["work_item_id"], existing["role_key"], existing["content"],
                        existing["provider"], existing["model"], float(existing["cost_usd"]),
                        existing["created_at"], int(existing["review_required"]),
                    )
                    if old != values:
                        raise ValueError("deliverable ID already exists with different content")
                else:
                    self._connection.execute(
                        "INSERT INTO deliverables (id,work_item_id,role_key,content,provider,model,cost_usd,created_at,review_required) VALUES(?,?,?,?,?,?,?,?,?)",
                        (str(deliverable.id), *values),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def save_deliverable_with_audit(self, deliverable: Any, record: AuditRecord) -> bool:
        """Persist a draft, move its task to review, and audit atomically."""
        if not deliverable.review_required:
            raise ValueError("worker deliverables must require review")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute("SELECT state FROM work_items WHERE id=?", (str(deliverable.work_item_id),)).fetchone()
                if item is None or item["state"] != TaskState.IN_PROGRESS.value:
                    self._connection.execute("ROLLBACK")
                    return False
                values = (str(deliverable.work_item_id), deliverable.role_key, deliverable.content, deliverable.provider, deliverable.model, float(deliverable.cost_usd), deliverable.created_at.isoformat(), 1)
                existing = self._connection.execute("SELECT * FROM deliverables WHERE id=?", (str(deliverable.id),)).fetchone()
                if existing is not None:
                    old = (existing["work_item_id"], existing["role_key"], existing["content"], existing["provider"], existing["model"], float(existing["cost_usd"]), existing["created_at"], int(existing["review_required"]))
                    if old != values:
                        raise ValueError("deliverable ID already exists with different content")
                else:
                    self._connection.execute("INSERT INTO deliverables (id,work_item_id,role_key,content,provider,model,cost_usd,created_at,review_required) VALUES(?,?,?,?,?,?,?,?,?)", (str(deliverable.id), *values))
                self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (TaskState.REVIEW.value, str(deliverable.work_item_id), TaskState.IN_PROGRESS.value))
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def review_work_item_with_audit(self, work_item_id: UUID, *, approved: bool, rationale: str, record: AuditRecord) -> TaskState | None:
        """Record an owner review decision and transition REVIEW atomically."""
        if not isinstance(approved, bool) or not rationale.strip() or len(rationale) > 2000:
            raise ValueError("review decision and a 1-2000 character rationale are required")
        target = TaskState.COMPLETED if approved else TaskState.READY
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute("SELECT state FROM work_items WHERE id=?", (str(work_item_id),)).fetchone()
                if item is None or item["state"] != TaskState.REVIEW.value:
                    self._connection.execute("ROLLBACK")
                    return None
                count = self._connection.execute("SELECT COUNT(*) AS n FROM deliverables WHERE work_item_id=? AND review_required=1", (str(work_item_id),)).fetchone()["n"]
                if int(count) < 1:
                    self._connection.execute("ROLLBACK")
                    raise ValueError("work item has no review-required deliverable")
                self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (target.value, str(work_item_id), TaskState.REVIEW.value))
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return target
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
    def fail_work_item_with_audit(self, work_item_id: UUID, record: AuditRecord) -> bool:
        """Move an in-progress task to failed only after its queue exhausts retries."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (TaskState.FAILED.value, str(work_item_id), TaskState.IN_PROGRESS.value))
                if cursor.rowcount != 1:
                    self._connection.execute("ROLLBACK")
                    return False
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def backup_to(self, destination: str | Path) -> Path:
        """Create and integrity-check a consistent SQLite snapshot at destination.

        The backup API includes committed WAL content and does not copy a live
        database file byte-for-byte. The caller is responsible for protecting
        and retaining the resulting file as sensitive company data.
        """
        destination_path = Path(destination).expanduser().resolve()
        if self.database != ":memory:":
            source_path = Path(self.database).expanduser().resolve()
            if destination_path == source_path:
                raise ValueError("backup destination must differ from the live database")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(destination_path), timeout=10)
            try:
                self._connection.backup(target, pages=256, sleep=0.05)
                integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError("SQLite backup failed its integrity check")
            except Exception:
                target.close()
                destination_path.unlink(missing_ok=True)
                raise
            else:
                target.close()
        return destination_path

    def list_deliverables(self, work_item_id: UUID) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM deliverables WHERE work_item_id=? ORDER BY created_at,id", (str(work_item_id),)).fetchall()
        return tuple({"id": row["id"], "work_item_id": row["work_item_id"], "role_key": row["role_key"], "content": row["content"], "provider": row["provider"], "model": row["model"], "cost_usd": float(row["cost_usd"]), "created_at": row["created_at"], "review_required": bool(row["review_required"])} for row in rows)

    def get_work_item(self, item_id: UUID) -> WorkItem | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM work_items WHERE id=?", (str(item_id),)
            ).fetchone()
        if row is None:
            return None
        return WorkItem(
            id=UUID(row["id"]), title=row["title"], objective=row["objective"],
            department=row["department"], state=TaskState(row["state"]),
            assigned_agent_id=UUID(row["assigned_agent_id"]) if row["assigned_agent_id"] else None,
            depends_on=tuple(UUID(value) for value in json.loads(row["dependencies_json"])),
            created_at=datetime.fromisoformat(row["created_at"]),
            business_id=row["business_id"] if "business_id" in row.keys() else "core",
        )

    def list_work_items(
        self, *, state: TaskState | None = None, business_id: str | None = None,
        limit: int = 100,
    ) -> tuple[WorkItem, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        clauses, values = [], []
        if state is not None:
            clauses.append("state=?")
            values.append(state.value)
        if business_id is not None:
            if not isinstance(business_id, str) or not _WORK_ITEM_BUSINESS_ID.fullmatch(business_id):
                raise ValueError("business_id must be a 2-63 character lowercase slug")
            clauses.append("business_id=?")
            values.append(business_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT id FROM work_items{where} ORDER BY created_at,id LIMIT ?",
                tuple(values),
            ).fetchall()
        return tuple(self.get_work_item(UUID(row["id"])) for row in rows)

    def append_audit_record(self, record: AuditRecord) -> str:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def verify_audit_chain(self) -> bool:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json,previous_hash,event_hash FROM audit_events ORDER BY sequence"
            ).fetchall()
        expected_previous = _ZERO_HASH
        for row in rows:
            payload = json.loads(row["payload_json"])
            if row["previous_hash"] != expected_previous:
                return False
            if payload.get("previous_hash") != expected_previous:
                return False
            if _digest(payload) != row["event_hash"]:
                return False
            expected_previous = row["event_hash"]
        return True

    def audit_event_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()
        return int(row["n"])


    def create_commercial_supplier(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Create a private supplier relationship scoped to one physical business."""
        unit = _assert_operational_commercial_scope(self._connection, self._lock, record.get("business_id"))
        if unit.get("delivery_class") != "physical-goods":
            raise ValueError("supplier records are available only to physical-goods business units")
        if record.get("business_id") == "physical-agency":
            if record.get("relationship_type") != "agency_supplier":
                raise ValueError("agency suppliers must remain in the physical-agency unit")
        elif record.get("business_id") == "physical-brand":
            if record.get("relationship_type") != "own_brand_supplier":
                raise ValueError("own-brand suppliers must remain in the physical-brand unit")
        elif record.get("relationship_type") != "supplier":
            raise ValueError("new physical business units must use the generic supplier relationship type")
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
        if business_id is not None:
            unit = _assert_operational_commercial_scope(self._connection, self._lock, business_id)
            if unit.get("delivery_class") != "physical-goods":
                raise ValueError("supplier records are available only to physical-goods business units")
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
                supplier = self._connection.execute(
                    "SELECT business_id FROM commercial_suppliers WHERE id=?", (supplier_id,)
                ).fetchone()
                if supplier is None:
                    self._connection.execute("ROLLBACK")
                    return False
                _assert_operational_commercial_scope(self._connection, self._lock, supplier["business_id"])
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
