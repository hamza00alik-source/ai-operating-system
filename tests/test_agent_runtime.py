from ai_os.db import initialize_database
from ai_os.agent_runtime import list_agent_runs, run_research_analyst


def test_research_analyst_runs_and_persists_output(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'agents.db'}")
    initialize_database()
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
    run = run_research_analyst("groq", "Assess demand for downloadable productivity templates.")

    assert run["status"] == "completed"
    assert run["provider"] == "groq"
    assert run["model"] == "mock-model"
    assert "demand is unverified" in run["output"]
    assert run["finished_at"]
    assert captured["provider"] == "groq"
    assert "Do not invent sources" in captured["prompt"]
    assert list_agent_runs()[0]["id"] == run["id"]


def test_research_analyst_records_failed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'agents.db'}")
    initialize_database()

    def fail_generate(provider, prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("ai_os.agent_runtime.generate", fail_generate)
    try:
        run_research_analyst("groq", "Analyze a simple business idea and its risks.")
        raise AssertionError("Expected provider failure")
    except RuntimeError as exc:
        assert "provider unavailable" in str(exc)

    runs = list_agent_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"] == "provider unavailable"
    assert runs[0]["finished_at"]
