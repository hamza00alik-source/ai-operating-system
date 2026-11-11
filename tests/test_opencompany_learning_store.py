from datetime import datetime, timezone

import pytest
from uuid import uuid4

from opencompany_core.domain import AuditRecord, TaskState, WorkItem
from opencompany_core.learning import ImprovementProposal, OutcomeEvaluation, OutcomeGrade, ProposalState
from opencompany_core.learning_store import LearningRepository
from opencompany_core.persistence import SQLiteStore


def audit(action, subject_type, subject_id):
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type=subject_type, subject_id=str(subject_id),
        outcome="recorded", correlation_id=str(uuid4()),
    )


def test_evaluation_proposal_decision_and_learning_note_are_durable(tmp_path):
    store = SQLiteStore(tmp_path / "learning.sqlite3")
    repository = LearningRepository(store._connection, store._lock)
    item = WorkItem(
        id=uuid4(), title="Assess buyer demand", objective="Create a sourced market report",
        department="intelligence-research", state=TaskState.COMPLETED,
    )
    store.save_work_item_with_audit(item, audit("test.completed", "work_item", item.id))
    evaluation = OutcomeEvaluation(
        id=uuid4(), work_item_id=item.id, evaluator="owner",
        grade=OutcomeGrade.SUCCESS,
        rubric_scores={"evidence_quality": 5, "scope_fit": 5, "completeness": 4},
        evidence_refs=(f"work_item:{item.id}",),
        observations="The report was useful; source freshness should be checked more consistently.",
    )
    repository.save_evaluation(evaluation, audit("learning.evaluated", "work_item", item.id))
    assert repository.list_evaluations(item.id)[0]["id"] == str(evaluation.id)

    proposal = ImprovementProposal(
        id=uuid4(), target="market_intelligence_analyst",
        change_summary="Add a source-freshness verification step.",
        rationale="The evaluation identified inconsistent freshness checks.",
        expected_measurement="Reduce stale-source findings in future reviews.",
        risk_level="low", based_on_evaluations=(evaluation.id,),
    )
    repository.save_proposal(proposal, audit("learning.proposed", "improvement_proposal", proposal.id))
    assert repository.decide_proposal(
        proposal.id, approved=True, owner_id="owner",
        rationale="Approved as role guidance.", record=audit("learning.approved", "improvement_proposal", proposal.id),
    )
    note_id = repository.save_learning_note(
        role_key="market_intelligence_analyst",
        note="Verify publication dates and prefer current primary sources.",
        evidence_refs=(f"evaluation:{evaluation.id}",),
        owner_id="owner", record=audit("learning.note_approved", "agent_role", "market_intelligence_analyst"),
    )
    notes = repository.list_learning_notes("market_intelligence_analyst")
    assert notes[0]["id"] == note_id
    assert "publication dates" in notes[0]["note"]
    assert store.verify_audit_chain()
    store.close()


def test_learning_notes_are_isolated_by_business_unit(tmp_path):
    store = SQLiteStore(tmp_path / "learning-business-scope.sqlite3")
    repository = LearningRepository(store._connection, store._lock)
    agency_item = WorkItem(
        id=uuid4(), title="Agency outcome", objective="Evaluate supplier research",
        department="intelligence-research", state=TaskState.COMPLETED,
        business_id="physical-agency",
    )
    digital_item = WorkItem(
        id=uuid4(), title="Digital outcome", objective="Evaluate product research",
        department="intelligence-research", state=TaskState.COMPLETED,
        business_id="digital-products",
    )
    store.save_work_item(agency_item)
    store.save_work_item(digital_item)
    agency_eval = OutcomeEvaluation(
        id=uuid4(), work_item_id=agency_item.id, evaluator="owner",
        grade=OutcomeGrade.SUCCESS, rubric_scores={"evidence": 5},
        evidence_refs=("source:agency-report",), observations="Supplier evidence was current.",
    )
    digital_eval = OutcomeEvaluation(
        id=uuid4(), work_item_id=digital_item.id, evaluator="owner",
        grade=OutcomeGrade.SUCCESS, rubric_scores={"evidence": 5},
        evidence_refs=("source:digital-report",), observations="Buyer evidence was current.",
    )
    repository.save_evaluation(agency_eval, audit("learning.evaluated", "work_item", agency_item.id))
    repository.save_evaluation(digital_eval, audit("learning.evaluated", "work_item", digital_item.id))

    agency_note = repository.save_learning_note(
        role_key="market_intelligence_analyst",
        note="Verify supplier certificates and export requirements.",
        evidence_refs=(f"evaluation:{agency_eval.id}",),
        owner_id="owner", record=audit("learning.note", "agent_role", "market_intelligence_analyst"),
        business_id="physical-agency",
    )
    digital_note = repository.save_learning_note(
        role_key="market_intelligence_analyst",
        note="Verify digital marketplace demand and platform fees.",
        evidence_refs=(f"evaluation:{digital_eval.id}",),
        owner_id="owner", record=audit("learning.note", "agent_role", "market_intelligence_analyst"),
        business_id="digital-products",
    )

    assert [note["id"] for note in repository.list_learning_notes("market_intelligence_analyst", "physical-agency")] == [agency_note]
    assert [note["id"] for note in repository.list_learning_notes("market_intelligence_analyst", "digital-products")] == [digital_note]
    with pytest.raises(ValueError, match="selected business unit"):
        repository.save_learning_note(
            role_key="market_intelligence_analyst",
            note="Cross-business note must be rejected.",
            evidence_refs=(f"evaluation:{agency_eval.id}",),
            owner_id="owner", record=audit("learning.note", "agent_role", "market_intelligence_analyst"),
            business_id="digital-products",
        )
    store.close()
