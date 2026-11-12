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
from .backup_persistence import BackupPersistenceMixin
from .schema_persistence import SchemaInitializationMixin
from .supplier_persistence import SupplierPersistenceMixin


class SQLiteStore(
    WorkItemPersistenceMixin,
    AgentPersistenceMixin,
    CommercialPersistenceMixin,
    DelegationPersistenceMixin,
    AuditPersistenceMixin,
    SchemaInitializationMixin,
    BackupPersistenceMixin,
    SupplierPersistenceMixin,
):
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

    def close(self) -> None:
        with self._lock:
            self._connection.close()
