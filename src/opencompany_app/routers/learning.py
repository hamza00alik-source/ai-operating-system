"""Owner-authenticated outcome evaluation and approved learning routes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import BUSINESS_UNIT_IDS, AuditRecord
from opencompany_core.learning import ImprovementProposal, OutcomeEvaluation, ProposalState
from opencompany_core.model_gateway import CostPolicyViolation, ModelRequest, NoEligibleProvider, ProviderUnavailable
from opencompany_core.persistence import SQLiteStore
from opencompany_core.workforce import default_workforce
from opencompany_app.api_schemas import (
    OutcomeEvaluationInput,
    ImprovementProposalInput,
    LearningAIProposalInput,
    LearningDecisionInput,
    LearningNoteInput,
)
from opencompany_app.api_dependencies import get_runtime, get_store, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


@router.post("/work-items/{item_id}/evaluations", dependencies=[Depends(require_owner_key)])
def create_outcome_evaluation(
    item_id: UUID,
    payload: OutcomeEvaluationInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    item = store.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    evaluation = OutcomeEvaluation(
        id=uuid4(), work_item_id=item_id, evaluator="owner",
        grade=payload.grade, rubric_scores=payload.rubric_scores,
        evidence_refs=tuple(payload.evidence_refs), observations=payload.observations,
    )
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.outcome_evaluated", subject_type="work_item",
        subject_id=str(item_id), outcome=evaluation.grade.value,
        correlation_id=str(uuid4()),
        details={"evaluation_id": str(evaluation.id), "rubric_scores": dict(evaluation.rubric_scores)},
    )
    try:
        runtime.learning.save_evaluation(evaluation, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": str(evaluation.id), "work_item_id": str(item_id),
        "grade": evaluation.grade.value, "rubric_scores": dict(evaluation.rubric_scores),
        "evidence_refs": list(evaluation.evidence_refs),
        "observations": evaluation.observations, "evaluated_at": evaluation.evaluated_at.isoformat(),
    }


@router.get("/work-items/{item_id}/evaluations", dependencies=[Depends(require_owner_key)])
def list_outcome_evaluations(
    item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    if store.get_work_item(item_id) is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    rows = runtime.learning.list_evaluations(item_id)
    return {"count": len(rows), "evaluations": rows}


@router.post("/learning/proposals", dependencies=[Depends(require_owner_key)])
def create_learning_proposal(
    payload: ImprovementProposalInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    proposal = ImprovementProposal(
        id=uuid4(), target=payload.target, change_summary=payload.change_summary,
        rationale=payload.rationale, expected_measurement=payload.expected_measurement,
        risk_level=payload.risk_level, based_on_evaluations=tuple(payload.based_on_evaluations),
        state=ProposalState.PROPOSED,
    )
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.improvement_proposed", subject_type="improvement_proposal",
        subject_id=str(proposal.id), outcome="proposed", correlation_id=str(uuid4()),
        details={"target": proposal.target, "risk_level": proposal.risk_level},
    )
    try:
        runtime.learning.save_proposal(proposal, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": str(proposal.id), "state": proposal.state.value, "owner_decision_required": True}


@router.post("/learning/ai-proposals", dependencies=[Depends(require_owner_key)])
def create_ai_learning_proposal(
    payload: LearningAIProposalInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    all_evaluations = runtime.learning.list_evaluations()
    by_id = {row["id"]: row for row in all_evaluations}
    selected = [by_id.get(str(value)) for value in payload.evaluation_ids]
    if any(item is None for item in selected):
        raise HTTPException(status_code=404, detail="One or more evaluation records were not found.")
    evidence_context = []
    supported_roles = set()
    for evaluation in selected:
        deliverables = store.list_deliverables(UUID(evaluation["work_item_id"]))
        by_deliverable = {item["id"]: item for item in deliverables}
        excerpts = []
        for ref in evaluation["evidence_refs"]:
            if ref.startswith("deliverable:"):
                artifact = by_deliverable.get(ref.split(":", 1)[1])
                if artifact:
                    supported_roles.add(artifact["role_key"])
                    excerpts.append({
                        "role_key": artifact["role_key"],
                        "content_excerpt": artifact["content"][:1800],
                    })
        evidence_context.append({
            "evaluation": evaluation,
            "deliverables": excerpts,
        })
    if len({item["business_id"] for item in selected}) != 1:
        raise HTTPException(status_code=409, detail="Learning analysis cannot combine evidence from different business units.")
    if not supported_roles:
        raise HTTPException(status_code=409, detail="Selected evaluations must cite deliverables with identifiable role keys.")
    business_id = selected[0]["business_id"]
    prompt = (
        "OPENCOMPANY EVIDENCE-BASED LEARNING REVIEW\n"
        f"Business unit: {business_id}. Use only evidence from this business unit.\n"
        "Recommend one narrowly scoped role-learning note based only on the supplied owner evaluations and artifacts. "
        "Do not claim a permanent code change. Return only JSON with exactly these keys: role_key, note, rationale, "
        "expected_measurement, risk_level. The role_key must be one of the supplied roles. The note should be a concise "
        "operating improvement that can be inserted into that role's future prompt only after owner approval.\n"
        f"Supported role keys: {json.dumps(sorted(supported_roles))}\n"
        f"Evidence: {json.dumps(evidence_context, ensure_ascii=False)}"
    )
    try:
        model_result = runtime.gateway.complete(
            ModelRequest(
                prompt=prompt, request_id=str(uuid4()), max_output_tokens=1800,
                business_id=business_id,
            ),
            request_budget_usd=0.0, preferred_provider="unorouter",
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=503, detail="No configured free model provider is available for learning analysis.") from exc
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        raise HTTPException(status_code=502, detail=f"Learning analysis failed safely: {type(exc).__name__}") from exc
    try:
        suggestion = json.loads(model_result.text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Learning model did not return valid JSON.") from exc
    expected_keys = {"role_key", "note", "rationale", "expected_measurement", "risk_level"}
    if not isinstance(suggestion, dict) or set(suggestion) != expected_keys:
        raise HTTPException(status_code=422, detail="Learning model returned an invalid proposal shape.")
    role_key = suggestion["role_key"]
    if role_key not in supported_roles:
        raise HTTPException(status_code=422, detail="Learning model selected a role not supported by the evidence.")
    try:
        default_workforce().get(role_key)
        proposal = ImprovementProposal(
            id=uuid4(), target=role_key, change_summary=suggestion["note"],
            rationale=suggestion["rationale"],
            expected_measurement=suggestion["expected_measurement"],
            risk_level=suggestion["risk_level"],
            based_on_evaluations=tuple(payload.evaluation_ids),
            state=ProposalState.PROPOSED,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Learning proposal failed validation: {exc}") from exc
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="agent", actor_id="learning-reviewer",
        action="learning.ai_proposal_created", subject_type="improvement_proposal",
        subject_id=str(proposal.id), outcome="proposed", correlation_id=str(uuid4()),
        details={"role_key": role_key, "business_id": business_id,
                 "provider": model_result.provider, "model": model_result.model},
    )
    try:
        runtime.learning.save_proposal(proposal, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": str(proposal.id), "target": proposal.target,
        "business_id": business_id,
        "change_summary": proposal.change_summary, "rationale": proposal.rationale,
        "expected_measurement": proposal.expected_measurement, "risk_level": proposal.risk_level,
        "state": proposal.state.value, "provider": model_result.provider,
        "model": model_result.model, "owner_approval_required": True,
        "note_applied": False,
    }


@router.post("/learning/proposals/{proposal_id}/apply-note", dependencies=[Depends(require_owner_key)])
def apply_approved_learning_proposal(
    proposal_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    proposal = next(
        (item for item in runtime.learning.list_proposals() if item["id"] == str(proposal_id)),
        None,
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Learning proposal not found.")
    if proposal["state"] != ProposalState.APPROVED.value:
        raise HTTPException(status_code=409, detail="Only owner-approved learning proposals can be applied.")
    try:
        default_workforce().get(proposal["target"])
    except LookupError as exc:
        raise HTTPException(status_code=409, detail="Proposal target is not a known workforce role.") from exc
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.approved_note_applied", subject_type="agent_role",
        subject_id=proposal["target"], outcome="applied", correlation_id=str(uuid4()),
        details={"proposal_id": str(proposal_id), "evidence_ids": proposal["based_on_evaluations"],
                 "business_id": proposal["business_id"]},
    )
    try:
        note_id = runtime.learning.apply_proposal_as_note(proposal_id, owner_id="owner", record=event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"proposal_id": str(proposal_id), "note_id": note_id, "role_key": proposal["target"], "state": "implemented"}


@router.get("/learning/proposals", dependencies=[Depends(require_owner_key)])
def list_learning_proposals(
    business_id: str | None = None,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    proposals = runtime.learning.list_proposals(business_id=business_id)
    return {"count": len(proposals), "business_id": business_id or "all", "proposals": proposals}


@router.post("/learning/proposals/{proposal_id}/decision", dependencies=[Depends(require_owner_key)])
def decide_learning_proposal(
    proposal_id: UUID,
    payload: LearningDecisionInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.improvement_decision", subject_type="improvement_proposal",
        subject_id=str(proposal_id), outcome="approved" if payload.approved else "rejected",
        correlation_id=str(uuid4()), details={"rationale": payload.rationale},
    )
    changed = runtime.learning.decide_proposal(
        proposal_id, approved=payload.approved, owner_id="owner",
        rationale=payload.rationale, record=event,
    )
    if not changed:
        raise HTTPException(status_code=409, detail="Proposal not found or already decided.")
    return {"id": str(proposal_id), "state": "approved" if payload.approved else "rejected"}


@router.post("/learning/notes", dependencies=[Depends(require_owner_key)])
def create_approved_learning_note(
    payload: LearningNoteInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        default_workforce().get(payload.role_key)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="Unknown role key.") from exc
    if payload.business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="learning.role_note_approved", subject_type="agent_role",
        subject_id=payload.role_key, outcome="approved", correlation_id=str(uuid4()),
        details={"evidence_refs": payload.evidence_refs, "business_id": payload.business_id},
    )
    try:
        note_id = runtime.learning.save_learning_note(
            role_key=payload.role_key, note=payload.note,
            evidence_refs=tuple(payload.evidence_refs), owner_id="owner", record=event,
            business_id=payload.business_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": note_id, "role_key": payload.role_key, "business_id": payload.business_id, "state": "approved"}


@router.get("/learning/notes/{role_key}", dependencies=[Depends(require_owner_key)])
def list_approved_learning_notes(
    role_key: str,
    business_id: str = "core",
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        default_workforce().get(role_key)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="Unknown role key.") from exc
    if business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    notes = runtime.learning.list_learning_notes(role_key, business_id=business_id)
    return {"role_key": role_key, "business_id": business_id, "count": len(notes), "notes": notes}
