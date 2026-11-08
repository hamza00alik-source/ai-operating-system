from ai_os.db import connect, initialize_database
from ai_os.agent_runtime import (
    claim_agent_run,
    enqueue_research_analyst,
    list_agent_runs,
    process_claimed_agent_run,
)


def test_research_analyst_queues_claims_and_persists_output(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'agents.db'}")
    initialize_database()
    run = enqueue_research_analyst(
        "groq", "Assess demand for downloadable productivity templates."
    )
    assert run["status"] == "queued"

    claimed = claim_agent_run(worker_id="worker-a")
    assert claimed is not None
    assert claimed["id"] == run["id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert claim_agent_run(worker_id="worker-b") is None

    captured = {}

    def fake_generate(provider, prompt):
        captured["provider"] = provider
        captured["prompt"] = prompt
        return {
            "provider": provider,
            "model": "mock-model",
            "response": "Summary: demand is unverified.\nNext: validate with customers.",
            "latency_ms": 12,
            "live": True,
        }

    monkeypatch.setattr("ai_os.agent_runtime.generate", fake_generate)
    completed = process_claimed_agent_run(claimed)
    assert completed["status"] == "completed"
    assert completed["provider"] == "groq"
    assert completed["model"] == "mock-model"
    assert "demand is unverified" in completed["output"]
    assert completed["finished_at"]
    assert completed["lease_owner"] is None
    assert captured["provider"] == "groq"
    assert "Do not invent sources" in captured["prompt"]
    assert list_agent_runs()[0]["id"] == run["id"]


def test_expired_agent_lease_can_be_reclaimed(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'agents.db'}")
    initialize_database()
    run = enqueue_research_analyst("groq", "Analyze a small business idea and its risks.")
    first = claim_agent_run(worker_id="worker-a")
    assert first["id"] == run["id"]

    with connect() as db:
        db.execute(
            "UPDATE agent_runs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (run["id"],),
        )

    recovered = claim_agent_run(worker_id="worker-b")
    assert recovered["id"] == run["id"]
    assert recovered["lease_owner"] == "worker-b"
    assert recovered["attempts"] == 2


def test_research_analyst_records_failed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'agents.db'}")
    initialize_database()
    enqueue_research_analyst("groq", "Analyze a simple business idea and its risks.")
    claimed = claim_agent_run(worker_id="worker-a")

    def fail_generate(provider, prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("ai_os.agent_runtime.generate", fail_generate)
    failed = process_claimed_agent_run(claimed)
    assert failed["status"] == "failed"
    assert failed["error"] == "provider unavailable"
    assert failed["finished_at"]
    assert failed["lease_owner"] is None
