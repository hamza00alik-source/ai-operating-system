"""Revocable owner sessions with hashed bearer tokens and CSRF binding."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import RLock


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OwnerSessionStore:
    """Session records share the core database transaction/lock boundary."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db = connection
        self._lock = lock
        with self._lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS owner_sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_owner_sessions_expiry ON owner_sessions(expires_at)"
            )

    def create(self, *, lifetime_hours: int = 168) -> tuple[str, str, datetime]:
        if not 1 <= lifetime_hours <= 168:
            raise ValueError("session lifetime must be between 1 and 168 hours")
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=lifetime_hours)
        with self._lock:
            self._db.execute(
                "INSERT INTO owner_sessions (token_hash,csrf_hash,created_at,expires_at,revoked_at) VALUES(?,?,?,?,NULL)",
                (_hash(token), _hash(csrf), now.isoformat(), expires.isoformat()),
            )
            self._db.execute("DELETE FROM owner_sessions WHERE expires_at<? OR revoked_at IS NOT NULL", (now.isoformat(),))
        return token, csrf, expires

    def validate(self, token: str, csrf: str | None = None, *, require_csrf: bool = False) -> bool:
        if not token or len(token) > 256:
            return False
        with self._lock:
            row = self._db.execute(
                "SELECT csrf_hash,expires_at,revoked_at FROM owner_sessions WHERE token_hash=?",
                (_hash(token),),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return False
        try:
            expiry = datetime.fromisoformat(row["expires_at"])
        except (TypeError, ValueError):
            return False
        if expiry <= datetime.now(timezone.utc):
            return False
        if require_csrf:
            return bool(csrf and hmac.compare_digest(row["csrf_hash"], _hash(csrf)))
        return True

    def rotate_csrf(self, token: str, current_csrf: str | None = None) -> tuple[str, datetime] | None:
        """Restore a browser's shared CSRF cookie, rotating only if it is missing or invalid."""
        if not token or len(token) > 256:
            return None
        now = datetime.now(timezone.utc)
        csrf = secrets.token_urlsafe(32)
        with self._lock:
            row = self._db.execute(
                "SELECT csrf_hash,expires_at,revoked_at FROM owner_sessions WHERE token_hash=?",
                (_hash(token),),
            ).fetchone()
            if row is None or row["revoked_at"] is not None:
                return None
            try:
                expires = datetime.fromisoformat(row["expires_at"])
            except (TypeError, ValueError):
                return None
            if expires <= now:
                return None
            if current_csrf and hmac.compare_digest(row["csrf_hash"], _hash(current_csrf)):
                return current_csrf, expires
            self._db.execute(
                "UPDATE owner_sessions SET csrf_hash=? WHERE token_hash=?",
                (_hash(csrf), _hash(token)),
            )
        return csrf, expires

    def revoke(self, token: str) -> bool:
        if not token or len(token) > 256:
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cursor = self._db.execute(
                "UPDATE owner_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (now, _hash(token)),
            )
        return cursor.rowcount == 1
