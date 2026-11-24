"""Canonical serialization and audit-chain primitives shared by persistence modules."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .domain import AuditRecord

_ZERO_HASH = "0" * 64


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _audit_payload(record: AuditRecord, previous_hash: str) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "occurred_at": record.occurred_at.isoformat(),
        "actor_type": record.actor_type,
        "actor_id": record.actor_id,
        "action": record.action,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "outcome": record.outcome,
        "correlation_id": record.correlation_id,
        "details": dict(record.details),
        "previous_hash": previous_hash,
    }


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
