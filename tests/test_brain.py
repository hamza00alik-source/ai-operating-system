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
