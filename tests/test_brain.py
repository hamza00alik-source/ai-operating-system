from ai_os.brain import brain_status, list_memories, record_experience, retrieve_memories, review_memory
from ai_os.db import initialize_database


def test_brain_persists_experience_and_requires_owner_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "brain.db"))
    initialize_database()

    record_experience("run-1", "task-1", "research", "Find product demand",
                      "A repeatable lesson: validate demand with current marketplace evidence.")
    status = brain_status()
    assert status["experiences"] == 1
    assert status["memories"]["proposed"] == 1
    assert status["memories"]["approved"] == 0
    assert retrieve_memories("marketplace demand evidence", "research") == []

    proposed = list_memories("proposed")
    assert len(proposed) == 1
    approved = review_memory(proposed[0]["id"], "approved", "Reviewed and accepted")
    assert approved["status"] == "approved"
    recalled = retrieve_memories("marketplace demand evidence", "research")
    assert len(recalled) == 1
    assert "validate demand" in recalled[0]["content"]


def test_brain_rejects_memory_review_decisions_outside_allowlist(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "brain-reject.db"))
    initialize_database()
    with pytest.raises(ValueError):
        review_memory("missing", "auto-approve")


def test_autonomous_learning_cycle_creates_evidence_based_proposal_and_is_idempotent(monkeypatch, tmp_path):
    from ai_os.brain import run_learning_cycle, record_failure_experience
    from ai_os.db import connect
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "brain-autonomy.db"))
    initialize_database()
    now = "2026-11-10T12:00:00+00:00"
    with connect() as db:
        db.execute("INSERT INTO tasks(id,title,department,business_id,status,created_at) VALUES(?,?,?,?,?,?)",
                   ("task-a", "Research demand", "research", "core", "completed", now))
        for i, status in enumerate(("completed", "failed", "partial"), 1):
            db.execute("INSERT INTO agent_runs(id,task_id,status,created_at) VALUES(?,?,?,?)",
                       (f"run-{i}", "task-a", status, now))
    record_failure_experience("run-f", "task-a", "research", "Research demand", "provider timeout")
    result = run_learning_cycle("core")
    assert result["proposals_created"] == 1
    assert result["proposals"][0]["department"] == "research"
    proposals = list_memories("proposed", business_id="core")
    assert any(item["category"] == "improvement" for item in proposals)
    second = run_learning_cycle("core")
    assert second["already_ran"] is True
    status = brain_status("core")
    assert status["autonomy"]["learning_cycles"] == 1
    assert status["autonomy"]["pending_improvement_proposals"] == 1


def test_learning_cycles_are_isolated_by_business(monkeypatch, tmp_path):
    from ai_os.brain import run_learning_cycle, brain_status
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "brain-isolation.db"))
    initialize_database()
    run_learning_cycle("physical-agency")
    assert brain_status("physical-agency")["autonomy"]["learning_cycles"] == 1
    assert brain_status("core")["autonomy"]["learning_cycles"] == 0
