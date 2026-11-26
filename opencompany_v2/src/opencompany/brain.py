"""Approved persistent memory with deterministic, scope-aware retrieval."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


class Brain:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection

    def initialize(self) -> None:
        self.db.execute("""CREATE TABLE IF NOT EXISTS memories(
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, topic TEXT NOT NULL,
            content TEXT NOT NULL, source TEXT NOT NULL, confidence REAL NOT NULL,
            approval TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        self.db.commit()

    def propose(self, scope: str, topic: str, content: str, source: str,
                confidence: float = 0.4) -> str:
        if not all(isinstance(value, str) and value.strip()
                   for value in (scope, topic, content, source)):
            raise ValueError("scope, topic, content and source are required")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be 0..1")
        memory_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)",
            (memory_id, scope, topic, content, source, float(confidence),
             "proposed", now),
        )
        self.db.commit()
        return memory_id

    def review(self, memory_id: str, approve: bool) -> bool:
        if not isinstance(approve, bool):
            raise TypeError("approve must be a boolean")
        status = "approved" if approve else "rejected"
        cur = self.db.execute(
            "UPDATE memories SET approval=? WHERE id=? AND approval='proposed'",
            (status, memory_id),
        )
        self.db.commit()
        return cur.rowcount == 1

    def recall(self, query: str, scope: str = "company", limit: int = 5) -> list[dict]:
        if not isinstance(query, str) or not query.strip():
            return []
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("scope is required")
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        words = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
        if not words:
            return []
        rows = self.db.execute(
            """SELECT * FROM memories
               WHERE approval='approved' AND scope IN (?, 'company')
               ORDER BY created_at DESC LIMIT 500""",
            (scope,),
        ).fetchall()
        ranked = []
        for row in rows:
            text = (row["topic"] + " " + row["content"]).lower()
            overlap = len(words & set(re.findall(r"[a-z0-9]{3,}", text)))
            if overlap:
                ranked.append((overlap / len(words), row["confidence"], row))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [dict(row) for _, _, row in ranked[:min(limit, 20)]]
