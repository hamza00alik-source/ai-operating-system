"""Evidence-based improvement proposals for OpenCompany.

The learning layer records outcomes and recommends controlled changes. It never
rewrites its own source code or applies operational changes autonomously.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping
from uuid import UUID

from .domain import _require_text, _require_utc


class OutcomeGrade(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    INCONCLUSIVE = "inconclusive"


class ProposalState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True)
class OutcomeEvaluation:
    id: UUID
    work_item_id: UUID
    evaluator: str
    grade: OutcomeGrade
    rubric_scores: Mapping[str, int]
    evidence_refs: tuple[str, ...]
    observations: str
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _require_text(self.evaluator, "evaluator", maximum=160)
        _require_text(self.observations, "observations", maximum=6000)
        _require_utc(self.evaluated_at, "evaluated_at")
        if not self.rubric_scores:
            raise ValueError("at least one rubric score is required")
        if any(not key.strip() or not 0 <= score <= 5
               for key, score in self.rubric_scores.items()):
            raise ValueError("rubric scores must use named criteria scored from 0 to 5")
        if not self.evidence_refs or any(not value.strip() for value in self.evidence_refs):
            raise ValueError("evaluations must include traceable evidence references")


@dataclass(frozen=True, slots=True)
class ImprovementProposal:
    id: UUID
    target: str
    change_summary: str
    rationale: str
    expected_measurement: str
    risk_level: str
    based_on_evaluations: tuple[UUID, ...]
    state: ProposalState = ProposalState.PROPOSED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    owner_decision: str | None = None

    def __post_init__(self) -> None:
        for name in ("target", "change_summary", "rationale", "expected_measurement", "risk_level"):
            _require_text(getattr(self, name), name, maximum=2000)
        _require_utc(self.created_at, "created_at")
        if not self.based_on_evaluations:
            raise ValueError("improvement proposals require evaluation evidence")
        if len(set(self.based_on_evaluations)) != len(self.based_on_evaluations):
            raise ValueError("evaluation references must be unique")
        if self.state in {ProposalState.APPROVED, ProposalState.REJECTED,
                          ProposalState.IMPLEMENTED, ProposalState.VERIFIED}:
            if not self.owner_decision:
                raise ValueError("non-proposed states require a recorded owner decision")


def create_improvement_proposal(
    evaluation: OutcomeEvaluation,
    *,
    target: str,
    change_summary: str,
    rationale: str,
    expected_measurement: str,
    risk_level: str,
) -> ImprovementProposal:
    """Turn one evaluation into a proposal; no code or settings are modified."""
    return ImprovementProposal(
        id=UUID(int=0), target=target, change_summary=change_summary,
        rationale=rationale, expected_measurement=expected_measurement,
        risk_level=risk_level, based_on_evaluations=(evaluation.id,),
        state=ProposalState.PROPOSED,
    )


def record_owner_decision(
    proposal: ImprovementProposal, *, approved: bool, owner_id: str, rationale: str
) -> ImprovementProposal:
    if proposal.state != ProposalState.PROPOSED:
        raise ValueError("only proposed improvements can receive an owner decision")
    _require_text(owner_id, "owner_id", maximum=160)
    _require_text(rationale, "rationale", maximum=2000)
    return ImprovementProposal(
        id=proposal.id, target=proposal.target,
        change_summary=proposal.change_summary, rationale=proposal.rationale,
        expected_measurement=proposal.expected_measurement, risk_level=proposal.risk_level,
        based_on_evaluations=proposal.based_on_evaluations,
        state=ProposalState.APPROVED if approved else ProposalState.REJECTED,
        created_at=proposal.created_at,
        owner_decision=f"{owner_id}: {rationale}",
    )
