"""Business-isolated, append-only memory for OpenCompany units."""
from __future__ import annotations
import re, sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4
from .persistence import _audit_payload, _digest, _json, _ZERO_HASH

_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_CATEGORY = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
_SECRET_MARKERS = ("-----begin private key-----", "api_key=", "access_token=", "password=")

class BusinessMemoryStore:
    """Versioned memory whose every query is constrained to one business scope."""
    def __init__(self, connection: sqlite3.Connection, lock: RLock):
        self._db, self._lock = connection, lock

    def _scope(self, business_id: str) -> str:
        if not isinstance(business_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", business_id):
            raise ValueError("business_id must be a 2-63 character lowercase slug")
        with self._lock:
            row = self._db.execute("SELECT memory_scope_id FROM opencompany_business_units WHERE business_id=?", (business_id,)).fetchone()
        if row is None:
            raise ValueError("unknown business unit")
        return row["memory_scope_id"]

    @staticmethod
    def _validate(memory_key: str, category: str, content: str) -> None:
        if not isinstance(memory_key, str) or not _SLUG.fullmatch(memory_key):
            raise ValueError("memory_key must be a 1-80 character lowercase slug")
        if not isinstance(category, str) or not _CATEGORY.fullmatch(category):
            raise ValueError("category must be a 2-40 character lowercase slug")
        if not isinstance(content, str) or not content.strip() or len(content) > 20000:
            raise ValueError("content must contain 1-20000 characters")
        if any(marker in content.casefold() for marker in _SECRET_MARKERS):
            raise ValueError("credentials and secret material must never be stored in business memory")

    def _audit(self, audit, business_id: str, memory_key: str, revision: int, outcome: str) -> None:
        if audit.actor_type != "owner":
            raise PermissionError("only owner-originated memory changes are enabled")
        previous = self._db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = previous["event_hash"] if previous else _ZERO_HASH
        from .domain import AuditRecord
        audited = AuditRecord(
            id=audit.id, occurred_at=audit.occurred_at, actor_type="owner", actor_id=audit.actor_id,
            action=audit.action, subject_type="business_memory", subject_id=f"{business_id}:{memory_key}",
            outcome=outcome, correlation_id=audit.correlation_id,
            details={"business_id":business_id,"memory_key":memory_key,"revision":revision},
        )
        payload = _audit_payload(audited, previous_hash)
        self._db.execute(
            "INSERT INTO audit_events(event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
            (str(audited.id),audited.occurred_at.isoformat(),_json(payload),previous_hash,_digest(payload)),
        )

    def put(self, business_id: str, memory_key: str, category: str, content: str, source: str, audit) -> dict[str, Any]:
        self._validate(memory_key,category,content)
        if not isinstance(source,str) or not source.strip() or len(source)>500:
            raise ValueError("source must contain 1-500 characters")
        if audit.actor_type != "owner":
            raise PermissionError("only owner-originated memory writes are enabled")
        scope=self._scope(business_id); now=datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row=self._db.execute("SELECT COALESCE(MAX(revision),0) revision FROM opencompany_business_memory_versions WHERE business_id=? AND memory_scope_id=? AND memory_key=?",(business_id,scope,memory_key)).fetchone()
                revision=int(row["revision"])+1
                old=self._db.execute("SELECT memory_id FROM opencompany_business_memory_versions WHERE business_id=? AND memory_scope_id=? AND memory_key=? ORDER BY revision LIMIT 1",(business_id,scope,memory_key)).fetchone()
                memory_id=old["memory_id"] if old else str(uuid4())
                self._db.execute("""INSERT INTO opencompany_business_memory_versions
                    (memory_id,business_id,memory_scope_id,memory_key,category,content,source,revision,operation,actor_type,actor_id,created_at)
                    VALUES(?,?,?,?,?,?,?,?,'upsert','owner',?,?)""",
                    (memory_id,business_id,scope,memory_key,category,content,source,revision,audit.actor_id,now))
                self._audit(audit,business_id,memory_key,revision,"stored")
                self._db.execute("COMMIT")
                return {"memory_id":memory_id,"business_id":business_id,"memory_key":memory_key,"category":category,"revision":revision,"operation":"upsert","created_at":now}
            except Exception:
                if self._db.in_transaction: self._db.execute("ROLLBACK")
                raise

    def forget(self, business_id: str, memory_key: str, audit) -> dict[str, Any] | None:
        if not isinstance(memory_key,str) or not _SLUG.fullmatch(memory_key): raise ValueError("invalid memory_key")
        if audit.actor_type != "owner": raise PermissionError("only owner-originated memory changes are enabled")
        scope=self._scope(business_id)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row=self._db.execute("""SELECT * FROM opencompany_business_memory_versions
                    WHERE business_id=? AND memory_scope_id=? AND memory_key=? ORDER BY revision DESC LIMIT 1""",(business_id,scope,memory_key)).fetchone()
                if row is None or row["operation"]=="tombstone":
                    self._db.execute("ROLLBACK"); return None
                revision=int(row["revision"])+1; now=datetime.now(timezone.utc).isoformat()
                self._db.execute("""INSERT INTO opencompany_business_memory_versions
                    (memory_id,business_id,memory_scope_id,memory_key,category,content,source,revision,operation,actor_type,actor_id,created_at)
                    VALUES(?,?,?,?,?,?,?,?,'tombstone','owner',?,?)""",
                    (row["memory_id"],business_id,scope,memory_key,row["category"],"","owner-requested removal",revision,audit.actor_id,now))
                self._audit(audit,business_id,memory_key,revision,"forgotten")
                self._db.execute("COMMIT")
                return {"business_id":business_id,"memory_key":memory_key,"revision":revision,"operation":"tombstone","created_at":now}
            except Exception:
                if self._db.in_transaction: self._db.execute("ROLLBACK")
                raise

    def list(self, business_id: str, *, category: str | None = None, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if not 1<=limit<=500: raise ValueError("limit must be between 1 and 500")
        scope=self._scope(business_id)
        if category is not None and (not isinstance(category,str) or not _CATEGORY.fullmatch(category)): raise ValueError("invalid category")
        sql="""SELECT v.* FROM opencompany_business_memory_versions v JOIN
            (SELECT memory_key,MAX(revision) revision FROM opencompany_business_memory_versions
             WHERE business_id=? AND memory_scope_id=? GROUP BY memory_key) latest
            ON latest.memory_key=v.memory_key AND latest.revision=v.revision
            WHERE v.business_id=? AND v.memory_scope_id=? AND v.operation='upsert'"""
        values: list[Any]=[business_id,scope,business_id,scope]
        if category is not None: sql+=" AND v.category=?"; values.append(category)
        sql+=" ORDER BY v.created_at DESC,v.memory_key LIMIT ?"; values.append(limit)
        with self._lock: rows=self._db.execute(sql,tuple(values)).fetchall()
        fields=("memory_id","business_id","memory_key","category","content","source","revision","operation","created_at")
        return tuple({k:row[k] for k in fields} for row in rows)

    def get(self,business_id: str,memory_key: str) -> dict[str,Any] | None:
        history=self.history(business_id,memory_key)
        if not history or history[0]["operation"]=="tombstone": return None
        return history[0]

    def history(self,business_id: str,memory_key: str) -> tuple[dict[str,Any],...]:
        scope=self._scope(business_id)
        with self._lock:
            rows=self._db.execute("""SELECT memory_id,business_id,memory_key,category,content,source,revision,operation,actor_type,actor_id,created_at
                FROM opencompany_business_memory_versions WHERE business_id=? AND memory_scope_id=? AND memory_key=? ORDER BY revision DESC""",(business_id,scope,memory_key)).fetchall()
        return tuple(dict(row) for row in rows)
