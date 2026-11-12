"""Commercial-domain SQLite repository operations mixed into SQLiteStore."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .domain import AuditRecord
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json


class CommercialPersistenceMixin:
    """Commercial records share the store's connection, lock and audit transaction."""
