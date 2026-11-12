"""Core domain records shared by OpenCompany subsystems."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass(frozen=True)
class AuditRecord:
    id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: str
    action: str
    subject_type: str
    subject_id: str
    outcome: str
    correlation_id: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.id, UUID):
            raise ValueError("audit id must be a UUID")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None:
            raise ValueError("audit timestamp must be timezone-aware")
        for name in ("actor_type", "actor_id", "action", "subject_type", "subject_id", "outcome", "correlation_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if not isinstance(self.details, dict):
            raise ValueError("audit details must be an object")
