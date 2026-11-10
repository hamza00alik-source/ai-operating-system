"""Structured peer-to-peer work exchange for OpenCompany.

Handoffs carry bounded task context and artifact references. They do not execute
tools, grant permissions, or bypass owner approval.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable
from uuid import UUID

from .domain import _require_text, _require_utc


class HandoffState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AgentHandoff:
    id: UUID
    work_item_id: UUID
    sender_agent_id: UUID
    recipient_agent_id: UUID
    purpose: str
    requested_result: str
    context: str
    artifact_ids: tuple[UUID, ...] = ()
    state: HandoffState = HandoffState.PROPOSED
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    updated_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    response_artifact_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if self.sender_agent_id == self.recipient_agent_id:
            raise ValueError("a handoff must involve two distinct agents")
        _require_text(self.purpose, "purpose", maximum=240)
        _require_text(self.requested_result, "requested_result", maximum=1200)
        _require_text(self.context, "context", maximum=6000)
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("input artifact identifiers must be unique")
        if len(set(self.response_artifact_ids)) != len(self.response_artifact_ids):
            raise ValueError("response artifact identifiers must be unique")
        if self.state == HandoffState.DELIVERED and not self.response_artifact_ids:
            raise ValueError("delivered handoffs must include response artifacts")


def accept_handoff(handoff: AgentHandoff, *, at: datetime) -> AgentHandoff:
    if handoff.state != HandoffState.PROPOSED:
        raise ValueError("only proposed handoffs can be accepted")
    _require_utc(at, "at")
    if at < handoff.created_at:
        raise ValueError("acceptance cannot precede handoff creation")
    return replace(handoff, state=HandoffState.ACCEPTED, updated_at=at)


def decline_handoff(handoff: AgentHandoff, *, at: datetime) -> AgentHandoff:
    if handoff.state != HandoffState.PROPOSED:
        raise ValueError("only proposed handoffs can be declined")
    _require_utc(at, "at")
    if at < handoff.created_at:
        raise ValueError("decline cannot precede handoff creation")
    return replace(handoff, state=HandoffState.DECLINED, updated_at=at)


def deliver_handoff(
    handoff: AgentHandoff, *, response_artifact_ids: Iterable[UUID], at: datetime
) -> AgentHandoff:
    if handoff.state != HandoffState.ACCEPTED:
        raise ValueError("only accepted handoffs can be delivered")
    _require_utc(at, "at")
    if at < handoff.updated_at:
        raise ValueError("delivery cannot precede acceptance")
    artifacts = tuple(response_artifact_ids)
    if not artifacts:
        raise ValueError("a delivery must include at least one result artifact")
    if len(set(artifacts)) != len(artifacts):
        raise ValueError("response artifact identifiers must be unique")
    return replace(
        handoff, state=HandoffState.DELIVERED,
        response_artifact_ids=artifacts, updated_at=at,
    )


def cancel_handoff(handoff: AgentHandoff, *, at: datetime) -> AgentHandoff:
    if handoff.state not in {HandoffState.PROPOSED, HandoffState.ACCEPTED}:
        raise ValueError("only open handoffs can be cancelled")
    _require_utc(at, "at")
    if at < handoff.updated_at:
        raise ValueError("cancellation cannot precede the latest handoff event")
    return replace(handoff, state=HandoffState.CANCELLED, updated_at=at)
