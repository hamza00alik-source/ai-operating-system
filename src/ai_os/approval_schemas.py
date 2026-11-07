"""API contracts for the CEO-to-owner approval gateway."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CEOApprovalRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(min_length=1, max_length=120)
    parameters: dict
    ttl_seconds: int = Field(default=900, ge=1, le=900)


class OwnerApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_hash: str = Field(min_length=64, max_length=64)
    decision: Literal["approved", "rejected"]

    @field_validator("action_hash")
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        if any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("action_hash must be a lowercase SHA-256 hex digest")
        return value


class OwnerApprovalRequestOut(BaseModel):
    id: str
    run_id: str
    requested_by: str
    action_type: str
    parameters: dict
    action_hash: str
    status: Literal["pending", "approved", "rejected", "consumed", "expired"]
    created_at: str
    expires_at: int
    decided_at: str | None = None
    decision: str | None = None
    consumed_at: str | None = None
    execution_id: str | None = None
