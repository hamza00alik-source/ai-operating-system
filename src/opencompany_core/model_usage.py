"""Durable, secret-free model usage ledger for owner cost visibility."""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any


class ModelUsageRepository:
    """Persist successful inference accounting on the core SQLite transaction boundary."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db = connection
        self._lock = lock
        with self._lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS model_usage (
                    request_id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL,
                    role_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_usd REAL NOT NULL CHECK(cost_usd >= 0),
                    recorded_at TEXT NOT NULL
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_usage_recorded ON model_usage(recorded_at)"
            )

    def record(self, event: dict[str, Any]) -> bool:
        required = ("request_id", "work_item_id", "role_key", "provider", "model")
        if any(not isinstance(event.get(key), str) or not event[key].strip() for key in required):
            raise ValueError("model usage identity fields are required")
        cost = float(event.get("cost_usd", 0.0))
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("model usage cost must be finite and non-negative")
        input_tokens = event.get("input_tokens")
        output_tokens = event.get("output_tokens")
        for value in (input_tokens, output_tokens):
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError("model usage token counts must be non-negative integers")
        recorded_at = datetime.now(timezone.utc).isoformat()
        values = (
            event["request_id"], event["work_item_id"], event["role_key"],
            event["provider"], event["model"], input_tokens, output_tokens,
            cost, recorded_at,
        )
        with self._lock:
            existing = self._db.execute(
                "SELECT work_item_id,role_key,provider,model,input_tokens,output_tokens,cost_usd "
                "FROM model_usage WHERE request_id=?", (event["request_id"],)
            ).fetchone()
            identity = values[1:8]
            if existing is not None:
                prior = tuple(existing[key] for key in (
                    "work_item_id", "role_key", "provider", "model",
                    "input_tokens", "output_tokens", "cost_usd",
                ))
                if prior != identity:
                    raise ValueError("model usage request ID already exists with different accounting")
                return False
            self._db.execute(
                """INSERT INTO model_usage
                   (request_id,work_item_id,role_key,provider,model,input_tokens,
                    output_tokens,cost_usd,recorded_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                values,
            )
        return True

    def summary(self, *, limit: int = 100) -> dict[str, Any]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        with self._lock:
            totals = self._db.execute(
                """SELECT COUNT(*) AS requests, COALESCE(SUM(cost_usd),0) AS cost_usd,
                          COALESCE(SUM(input_tokens),0) AS input_tokens,
                          COALESCE(SUM(output_tokens),0) AS output_tokens
                   FROM model_usage"""
            ).fetchone()
            rows = self._db.execute(
                """SELECT request_id,work_item_id,role_key,provider,model,input_tokens,
                          output_tokens,cost_usd,recorded_at
                   FROM model_usage ORDER BY recorded_at DESC,request_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return {
            "request_count": int(totals["requests"]),
            "total_cost_usd": float(totals["cost_usd"]),
            "total_input_tokens": int(totals["input_tokens"]),
            "total_output_tokens": int(totals["output_tokens"]),
            "events": [dict(row) for row in rows],
        }
