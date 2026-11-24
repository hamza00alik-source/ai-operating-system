"""Owner-reviewed persistent Brain memory for primary OpenCompany execution."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


class BrainMemoryRepository:
    """SQLite memory proposals; only owner-approved records enter agent context."""

    def __init__(self, db: sqlite3.Connection, lock):
        self._db, self._lock = db, lock
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS opencompany_brain_memories(
              id TEXT PRIMARY KEY,scope TEXT NOT NULL,topic TEXT NOT NULL,
              content TEXT NOT NULL,source TEXT NOT NULL,confidence REAL NOT NULL,
              approval TEXT NOT NULL,created_at TEXT NOT NULL,reviewed_at TEXT,
              review_note TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_opencompany_brain_scope
              ON opencompany_brain_memories(scope,approval,created_at);
            """)
            db.commit()

    def propose(self, scope: str, topic: str, content: str, source: str,
                confidence: float = 0.4) -> dict:
        values = (scope, topic, content, source)
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("scope, topic, content and source are required")
        if len(scope) > 180 or len(topic) > 240 or len(content) > 12000 or len(source) > 500:
            raise ValueError("memory field exceeds its maximum length")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        record = {
            "id": str(uuid4()), "scope": scope.strip(), "topic": topic.strip(),
            "content": content.strip(), "source": source.strip(),
            "confidence": float(confidence), "approval": "proposed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._db.execute(
                """INSERT INTO opencompany_brain_memories
                   (id,scope,topic,content,source,confidence,approval,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                tuple(record[key] for key in (
                    "id", "scope", "topic", "content", "source",
                    "confidence", "approval", "created_at"
                )),
            )
            self._db.commit()
        return record

    def review(self, memory_id: str, approve: bool, note: str = "") -> dict | None:
        if not isinstance(approve, bool):
            raise TypeError("approve must be a boolean")
        if not isinstance(note, str) or len(note) > 1200:
            raise ValueError("review note must be text of at most 1200 characters")
        now = datetime.now(timezone.utc).isoformat()
        status = "approved" if approve else "rejected"
        with self._lock:
            cursor = self._db.execute(
                """UPDATE opencompany_brain_memories
                   SET approval=?,reviewed_at=?,review_note=?
                   WHERE id=? AND approval='proposed'""",
                (status, now, note.strip(), str(memory_id)),
            )
            self._db.commit()
            if cursor.rowcount != 1:
                return None
            row = self._db.execute(
                "SELECT * FROM opencompany_brain_memories WHERE id=?",
                (str(memory_id),),
            ).fetchone()
        return dict(row)

    def get(self, memory_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM opencompany_brain_memories WHERE id=?",
                (str(memory_id),),
            ).fetchone()
        return dict(row) if row else None

    def list(self, approval: str | None = None, scope: str | None = None,
             limit: int = 100) -> list[dict]:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        clauses, params = [], []
        if approval is not None:
            if approval not in {"proposed", "approved", "rejected"}:
                raise ValueError("invalid approval state")
            clauses.append("approval=?")
            params.append(approval)
        if scope is not None:
            clauses.append("scope=?")
            params.append(scope)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM opencompany_brain_memories" + where
                + " ORDER BY created_at DESC LIMIT ?",
                (*params, min(limit, 500)),
            ).fetchall()
        return [dict(row) for row in rows]

    def recall(self, query: str, *, scopes: tuple[str, ...], limit: int = 12) -> list[dict]:
        if not isinstance(query, str) or not query.strip():
            return []
        if not isinstance(scopes, tuple) or not scopes or any(
            not isinstance(scope, str) or not scope.strip() for scope in scopes
        ):
            raise ValueError("one or more valid scopes are required")
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        words = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
        if not words:
            return []
        allowed_scopes = tuple(dict.fromkeys((*scopes, "company")))
        placeholders = ",".join("?" for _ in allowed_scopes)
        with self._lock:
            rows = self._db.execute(
                f"""SELECT * FROM opencompany_brain_memories
                    WHERE approval='approved' AND scope IN ({placeholders})
                    ORDER BY created_at DESC LIMIT 500""",
                allowed_scopes,
            ).fetchall()
        ranked = []
        for row in rows:
            candidate_words = set(re.findall(
                r"[a-z0-9]{3,}", (row["topic"] + " " + row["content"]).lower()
            ))
            overlap = len(words & candidate_words)
            if overlap:
                ranked.append((overlap / len(words), row["confidence"], row))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [dict(row) for _, _, row in ranked[:min(limit, 30)]]
