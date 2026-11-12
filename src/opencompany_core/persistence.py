"""Local durable storage for the independent OpenCompany core.

SQLite is used as a small, inspectable persistence layer. All writes are
transactional; audit events are linked with SHA-256 hashes to make later
alteration detectable. This is tamper-evident, not a substitute for backups
or access controls.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from .commercial_persistence import CommercialPersistenceMixin
from .delegation_persistence import DelegationPersistenceMixin
from .audit_persistence import AuditPersistenceMixin
from .agent_persistence import AgentPersistenceMixin
from .work_item_persistence import WorkItemPersistenceMixin


_SCHEMA_VERSION = 7


class SQLiteStore(WorkItemPersistenceMixin, AgentPersistenceMixin, CommercialPersistenceMixin, DelegationPersistenceMixin, AuditPersistenceMixin):
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
                return
            raise RuntimeError(f"unsupported database schema version: {version}")


    def close(self) -> None:
        with self._lock:
            self._connection.close()

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
