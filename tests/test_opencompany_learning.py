from datetime import datetime, timezone
from uuid import uuid4

import pytest

from opencompany_core.learning import (
    ImprovementProposal, OutcomeEvaluation, OutcomeGrade, ProposalState,
    create_improvement_proposal, record_owner_decision,
)


def evaluation():
    return OutcomeEvaluation(
        id=uuid4(), work_item_id=uuid4(), evaluator="quality_reviewer",
        grade=OutcomeGrade.PARTIAL,
        rubric_scores={"accuracy": 4, "completeness": 2},
        evidence_refs=("artifact://report/1",),
        observations="The report was accurate but missed two required sections.",
    )


def test_evaluation_requires_evidence_and_scored_criteria():
    with pytest.raises(ValueError, match="evidence references"):
        OutcomeEvaluation(uuid4(), uuid4(), "reviewer", OutcomeGrade.SUCCESS,
                          {"accuracy": 5}, (), "Looks good")
    with pytest.raises(ValueError, match="0 to 5"):
        OutcomeEvaluation(uuid4(), uuid4(), "reviewer", OutcomeGrade.SUCCESS,
                          {"accuracy": 8}, ("artifact://1",), "Looks good")


def test_evaluation_generates_proposal_without_applying_it():
    record = evaluation()
    proposal = create_improvement_proposal(
        record, target="research workflow",
        change_summary="Add a required evidence coverage check",
        rationale="The evaluation identified missing sections.",
        expected_measurement="Completeness score improves in the next five reviewed runs.",
        risk_level="low",
    )
    assert proposal.state is ProposalState.PROPOSED
    assert proposal.based_on_evaluations == (record.id,)
    assert proposal.owner_decision is None


def test_proposal_requires_owner_decision_before_approval_state():
    with pytest.raises(ValueError, match="owner decision"):
        ImprovementProposal(
            uuid4(), "workflow", "Change", "Reason", "Measure", "low",
            (uuid4(),), state=ProposalState.APPROVED,
        )


def test_owner_can_approve_or_reject_proposal_with_rationale():
    record = evaluation()
    proposal = create_improvement_proposal(
        record, target="task planning", change_summary="Improve acceptance criteria",
        rationale="Evaluation evidence shows ambiguity.",
        expected_measurement="Fewer rework cycles", risk_level="low",
    )
    approved = record_owner_decision(
        proposal, approved=True, owner_id="owner",
        rationale="Approved for a separate test branch.",
    )
    rejected = record_owner_decision(
        proposal, approved=False, owner_id="owner",
        rationale="Insufficient evidence.",
    )
    assert approved.state is ProposalState.APPROVED
    assert rejected.state is ProposalState.REJECTED


def test_decided_proposal_cannot_be_decided_again():
    record = evaluation()
    proposal = create_improvement_proposal(
        record, target="workflow", change_summary="Change", rationale="Evidence",
        expected_measurement="Measure", risk_level="low",
    )
    approved = record_owner_decision(
        proposal, approved=True, owner_id="owner", rationale="Proceed to isolated tests",
    )
    with pytest.raises(ValueError, match="only proposed"):
        record_owner_decision(
            approved, approved=False, owner_id="owner", rationale="Changed mind",
        )
