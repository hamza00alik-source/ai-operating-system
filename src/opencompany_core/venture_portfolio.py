"""Owner-governed opportunity portfolio for discovering any viable business model.

This registry is intentionally separate from operating business units. A
validated opportunity is not a business until the owner explicitly approves
its launch and provisions a separate operating unit.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

_STATUSES = {"discovered", "researching", "validated", "rejected", "approved_to_launch", "launched"}
_TRANSITIONS = {
    "discovered": {"researching", "rejected"},
    "researching": {"validated", "rejected"},
    "validated": {"researching", "rejected", "approved_to_launch"},
    "rejected": {"researching"},
    "approved_to_launch": {"launched"},
    "launched": set(),
}
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class VenturePortfolioError(ValueError):
    """Invalid opportunity data or lifecycle transition."""


class VenturePortfolio:
    """SQLite-backed portfolio. All mutations are owner-authenticated by the API."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock):
        self._db = connection
        self._lock = lock
        with self._lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS venture_opportunities (
                    id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    business_model TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_market TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('discovered','researching','validated','rejected','approved_to_launch','launched')),
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    owner_decision TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS venture_portfolio_events (
                    id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL REFERENCES venture_opportunities(id),
                    action TEXT NOT NULL,
                    previous_status TEXT,
                    new_status TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    rationale TEXT,
                    occurred_at TEXT NOT NULL
                )
            """)
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_venture_portfolio_status ON venture_opportunities(status, updated_at)")
            # Preserve the event history as append-only evidence at the database layer.
            self._db.execute("""
                CREATE TRIGGER IF NOT EXISTS venture_events_no_update
                BEFORE UPDATE ON venture_portfolio_events
                BEGIN SELECT RAISE(ABORT, 'venture portfolio events are append-only'); END
            """)
            self._db.execute("""
                CREATE TRIGGER IF NOT EXISTS venture_events_no_delete
                BEFORE DELETE ON venture_portfolio_events
                BEGIN SELECT RAISE(ABORT, 'venture portfolio events are append-only'); END
            """)

    @staticmethod
    def _validate_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
        if len(evidence) > 20:
            raise VenturePortfolioError("at most 20 evidence references are allowed")
        result = []
        for item in evidence:
            url = str(item.get("url", "")).strip()
            note = str(item.get("note", "")).strip()
            if not url.startswith("https://") or len(url) > 2000:
                raise VenturePortfolioError("evidence URLs must be HTTPS and at most 2000 characters")
            result.append({"url": url, "note": note[:1000]})
        return result

    def create(self, *, title: str, slug: str, business_model: str,
               description: str, target_market: str,
               evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        values = [title.strip(), business_model.strip(), description.strip(), target_market.strip()]
        limits = [160, 80, 5000, 300]
        if any(not value or len(value) > limit for value, limit in zip(values, limits)):
            raise VenturePortfolioError("title, model, description, or target market is empty or too long")
        if not _SLUG.fullmatch(slug):
            raise VenturePortfolioError("slug must be 2-63 lowercase letters, numbers, or hyphens")
        refs = self._validate_evidence(evidence or [])
        now = datetime.now(timezone.utc).isoformat()
        item_id = str(uuid4())
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    """INSERT INTO venture_opportunities
                    (id,slug,title,business_model,description,target_market,status,evidence_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,'discovered',?,?,?)""",
                    (item_id, slug, values[0], values[1], values[2], values[3],
                     json.dumps(refs, ensure_ascii=False), now, now),
                )
                self._db.execute(
                    """INSERT INTO venture_portfolio_events
                    (id,opportunity_id,action,previous_status,new_status,actor,rationale,occurred_at)
                    VALUES(?,?,'created',NULL,'discovered','owner',NULL,?)""",
                    (str(uuid4()), item_id, now),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise VenturePortfolioError("an opportunity with this slug already exists") from exc
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        return self.get(item_id)

    def get(self, opportunity_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM venture_opportunities WHERE id=?", (opportunity_id,)).fetchone()
        return self._decode(row) if row else None

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json"))
        return item

    def list(self, *, status: str | None = None, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if status is not None and status not in _STATUSES:
            raise VenturePortfolioError("unknown portfolio status")
        if not 1 <= limit <= 500:
            raise VenturePortfolioError("limit must be between 1 and 500")
        query = "SELECT * FROM venture_opportunities"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY updated_at DESC, id LIMIT ?"
        with self._lock:
            rows = self._db.execute(query, (*params, limit)).fetchall()
        return tuple(self._decode(row) for row in rows)

    def transition(self, opportunity_id: str, *, status: str, rationale: str,
                   confirm_owner_approval: bool = False) -> dict[str, Any] | None:
        if status not in _STATUSES:
            raise VenturePortfolioError("unknown portfolio status")
        if len(rationale.strip()) > 2000:
            raise VenturePortfolioError("rationale must be at most 2000 characters")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute("SELECT status FROM venture_opportunities WHERE id=?", (opportunity_id,)).fetchone()
                if row is None:
                    self._db.execute("ROLLBACK")
                    return None
                previous = row["status"]
                if status not in _TRANSITIONS[previous]:
                    raise VenturePortfolioError("invalid opportunity lifecycle transition")
                if status == "approved_to_launch" and not confirm_owner_approval:
                    raise VenturePortfolioError("explicit owner approval is required before launch planning")
                if status == "launched" and not confirm_owner_approval:
                    raise VenturePortfolioError("explicit owner confirmation is required to record launch")
                self._db.execute(
                    "UPDATE venture_opportunities SET status=?,owner_decision=?,updated_at=? WHERE id=?",
                    (status, rationale.strip() or None, now, opportunity_id),
                )
                self._db.execute(
                    """INSERT INTO venture_portfolio_events
                    (id,opportunity_id,action,previous_status,new_status,actor,rationale,occurred_at)
                    VALUES(?,?,'status_changed',?,?,'owner',?,?)""",
                    (str(uuid4()), opportunity_id, previous, status, rationale.strip() or None, now),
                )
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        return self.get(opportunity_id)

    def events(self, opportunity_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM venture_portfolio_events WHERE opportunity_id=? ORDER BY occurred_at,id",
                (opportunity_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)
