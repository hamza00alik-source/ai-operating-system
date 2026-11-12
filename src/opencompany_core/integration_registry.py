"""Business-scoped integration registry.

This module records integration intent only. It never opens network connections,
executes provider actions, grants permissions, or activates business units.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from .domain import AuditRecord


_PROVIDER_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_CREDENTIAL_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_PERMISSION = re.compile(r"^[a-z][a-z0-9:_-]{1,79}$")


class BusinessIntegrationRegistry:
    """Persist integration declarations under immutable business-specific scopes."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db, self._lock = connection, lock
        with self._lock:
            required = {
                "opencompany_business_integrations",
                "opencompany_business_integration_events",
            }
            present = {
                row["name"] for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not required.issubset(present):
                raise RuntimeError("business integration schema migration is required")

    def register(
        self, business_id: str, *, provider_key: str, display_name: str,
        credential_key: str, permissions: list[str], audit: AuditRecord,
        rationale: str = "",
    ) -> dict[str, Any]:
        if audit.actor_type != "owner":
            raise PermissionError("only an authenticated owner can register an integration")
        if not isinstance(business_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", business_id):
            raise ValueError("invalid business unit identifier")
        if not isinstance(provider_key, str) or not _PROVIDER_KEY.fullmatch(provider_key):
            raise ValueError("provider_key must be a lowercase provider identifier")
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 160:
            raise ValueError("display_name must contain 1-160 characters")
        if not isinstance(credential_key, str) or not _CREDENTIAL_KEY.fullmatch(credential_key):
            raise ValueError("credential_key must be a valid business credential identifier")
        if not isinstance(permissions, list) or not 1 <= len(permissions) <= 20:
            raise ValueError("permissions must contain 1-20 declared permission identifiers")
        if any(not isinstance(item, str) or not _PERMISSION.fullmatch(item) for item in permissions):
            raise ValueError("permissions must use bounded lowercase permission identifiers")
        if len(set(permissions)) != len(permissions):
            raise ValueError("duplicate permissions are not allowed")
        if not isinstance(rationale, str) or len(rationale) > 1000:
            raise ValueError("rationale must be at most 1000 characters")
        now = datetime.now(timezone.utc).isoformat()
        integration_id = str(uuid4())
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                unit = self._db.execute(
                    "SELECT integration_scope_id,credential_scope_id,status FROM opencompany_business_units WHERE business_id=?",
                    (business_id,),
                ).fetchone()
                if unit is None:
                    raise ValueError("unknown business unit")
                if unit["status"] == "paused":
                    raise ValueError("integrations cannot be registered for a paused business unit")
                credential_scope_id = unit["credential_scope_id"]
                credential = self._db.execute(
                    """SELECT 1 FROM opencompany_business_credentials
                       WHERE business_id=? AND credential_scope_id=? AND credential_key=?""",
                    (business_id, credential_scope_id, credential_key),
                ).fetchone()
                if credential is None:
                    raise ValueError("credential_key must refer to a stored credential in this business unit")
                self._db.execute(
                    """INSERT INTO opencompany_business_integrations
                       (integration_id,business_id,integration_scope_id,provider_key,display_name,
                        credential_scope_id,credential_key,permissions_json,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,'pending_review',?,?)""",
                    (integration_id, business_id, unit["integration_scope_id"], provider_key,
                     display_name.strip(), credential_scope_id, credential_key,
                     json.dumps(sorted(permissions), separators=(",", ":")), now, now),
                )
                self._db.execute(
                    """INSERT INTO opencompany_business_integration_events
                       (event_id,integration_id,business_id,integration_scope_id,action,
                        actor_type,actor_id,rationale,occurred_at)
                       VALUES(?,?,?,?,'registered','owner',?,?,?)""",
                    (str(uuid4()), integration_id, business_id, unit["integration_scope_id"],
                     audit.actor_id, rationale, now),
                )
                from .persistence import _ZERO_HASH, _audit_payload, _digest, _json
                previous = self._db.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                audited = AuditRecord(
                    id=audit.id, occurred_at=audit.occurred_at, actor_type="owner",
                    actor_id=audit.actor_id, action=audit.action,
                    subject_type="business_integration", subject_id=integration_id,
                    outcome="pending_review", correlation_id=audit.correlation_id,
                    details={
                        **dict(audit.details), "business_id": business_id,
                        "provider_key": provider_key, "credential_key": credential_key,
                        "permissions": sorted(permissions), "network_connection_attempted": False,
                    },
                )
                payload = _audit_payload(audited, previous_hash)
                self._db.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(audited.id), audited.occurred_at.isoformat(), _json(payload),
                     previous_hash, _digest(payload)),
                )
                self._db.execute("COMMIT")
                return {
                    "integration_id": integration_id, "business_id": business_id,
                    "provider_key": provider_key, "display_name": display_name.strip(),
                    "credential_key": credential_key, "permissions": sorted(permissions),
                    "status": "pending_review", "network_connection_attempted": False,
                }
            except sqlite3.IntegrityError as exc:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise ValueError("integration already exists or violates business-scope constraints") from exc
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def list(self, business_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            if self._db.execute(
                "SELECT 1 FROM opencompany_business_units WHERE business_id=?", (business_id,)
            ).fetchone() is None:
                raise ValueError("unknown business unit")
            rows = self._db.execute(
                """SELECT integration_id,business_id,provider_key,display_name,credential_key,
                          permissions_json,status,created_at,updated_at
                   FROM opencompany_business_integrations WHERE business_id=?
                   ORDER BY created_at,integration_id""",
                (business_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["permissions"] = json.loads(item.pop("permissions_json"))
            item["network_connection_enabled"] = False
            result.append(item)
        return tuple(result)

    def events(self, business_id: str, integration_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._db.execute(
                """SELECT event_id,integration_id,business_id,action,actor_type,actor_id,
                          rationale,occurred_at
                   FROM opencompany_business_integration_events
                   WHERE business_id=? AND integration_id=?
                   ORDER BY occurred_at,event_id""",
                (business_id, integration_id),
            ).fetchall()
        return tuple(dict(row) for row in rows)
