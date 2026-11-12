"""Business-unit registry; identities are explicit and isolated."""
from __future__ import annotations
import sqlite3

_DEFAULT_UNITS = (
    ("physical-agency", "Physical Products Agency"),
    ("physical-brand", "Owned Physical Products Brand"),
    ("digital-products", "Digital Products"),
)

class BusinessUnitRegistry:
    def __init__(self, connection: sqlite3.Connection, lock):
        self.connection, self.lock = connection, lock
        with self.lock:
            self.connection.execute("""CREATE TABLE IF NOT EXISTS opencompany_business_units (
                business_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            self.connection.executemany(
                "INSERT OR IGNORE INTO opencompany_business_units(business_id,name) VALUES(?,?)",
                _DEFAULT_UNITS,
            )
            self.connection.commit()

    def list(self):
        with self.lock:
            rows = self.connection.execute(
                "SELECT business_id,name,status,created_at FROM opencompany_business_units ORDER BY business_id"
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def get(self, business_id: str):
        with self.lock:
            row = self.connection.execute(
                "SELECT business_id,name,status,created_at FROM opencompany_business_units WHERE business_id=?",
                (business_id,),
            ).fetchone()
        return dict(row) if row else None

    def require_active(self, business_id: str):
        unit = self.get(business_id)
        if unit is None or unit["status"] != "active":
            raise ValueError("business unit not found or inactive")
        return unit
