"""Small thread-safe SQLite persistence boundary for OpenCompany."""
from __future__ import annotations
import sqlite3
import threading
from pathlib import Path

class SQLiteStore:
    def __init__(self, database_path: str | Path):
        self.path = str(database_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def transaction(self):
        return _Transaction(self._connection, self._lock)

class _Transaction:
    def __init__(self, connection, lock):
        self.connection, self.lock = connection, lock
    def __enter__(self):
        self.lock.acquire()
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection
    def __exit__(self, exc_type, exc, tb):
        try:
            self.connection.rollback() if exc_type else self.connection.commit()
        finally:
            self.lock.release()
