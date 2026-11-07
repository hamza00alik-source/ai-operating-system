import pytest

from ai_os.db import connect, initialize_database
from ai_os.improvement import (
    draft_improvement_proposals,
    list_improvement_proposals,
    review_improvement_proposal,
)


def _seed_evaluation_db(path, monkeypatch, count=2):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{path}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO company_runs (id,title,description,status,created_at,updated_at) "
            "VALUES ('proposal-run','Proposal test','','running','2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"
        )
        for index in range(count):
            db.execute(
                """INSERT INTO company_run_steps
                (run_id,step_key,agent_id,task,context,depends_on_json,status,position,created_at,updated_at)
                VALUES ('proposal-run',?,'researcher','Task','','[]','completed',?,
                        '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')""",
                (f"step-{index}", index),
            )
            db.execute(
                """INSERT INTO agent_evaluations
                (id,run_id,step_key,agent_id,evaluator_version,score,passed,
                 critical_failures_json,checks_json,limitations_json,created_at)
                VALUES (?, 'proposal-run', ?, 'researcher','1.0.0',75,0,'[]',
                        '[{"key":"completed_has_evidence","passed":false,"weight":15}]',
                        '[]',?)""",
                (f"evaluation-{index}", f"step-{index}", f"2026-11-06T00:00:0{index}Z"),
            )


def test_repeated_failures_generate_evidence_linked_candidate_only(tmp_path, monkeypatch):
    _seed_evaluation_db(tmp_path / "proposal.sqlite3", monkeypatch)
    created = draft_improvement_proposals()
    assert len(created) == 1
    proposal = created[0]
    assert proposal["status"] == "candidate"
    assert proposal["agent_id"] == "researcher"
    assert len(proposal["evidence"]) == 2
    assert "evidence" in proposal["proposed_change"].lower()
    assert list_improvement_proposals(status="candidate")[0]["id"] == proposal["id"]
    assert draft_improvement_proposals() == []


def test_single_failure_does_not_generate_proposal(tmp_path, monkeypatch):
    _seed_evaluation_db(tmp_path / "single.sqlite3", monkeypatch, count=1)
    assert draft_improvement_proposals() == []


def test_owner_review_is_one_time_and_never_marks_adopted(tmp_path, monkeypatch):
    _seed_evaluation_db(tmp_path / "review.sqlite3", monkeypatch)
    proposal = draft_improvement_proposals()[0]
    reviewed = review_improvement_proposal(
        proposal["id"], decision="approved_for_testing",
        actor="owner:test", note="Run the regression suite first.",
    )
    assert reviewed["status"] == "approved_for_testing"
    assert reviewed["reviewed_by"] == "owner:test"
    with pytest.raises(ValueError, match="reviewed once"):
        review_improvement_proposal(
            proposal["id"], decision="rejected", actor="owner:test"
        )
    assert reviewed["status"] != "adopted"
