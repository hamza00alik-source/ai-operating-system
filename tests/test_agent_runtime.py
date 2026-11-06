from fastapi.testclient import TestClient

from ai_os.api import app


def _run_payload():
    return {
        "title": "Runtime agent handoff test",
        "description": "Two specialists work in dependency order.",
        "steps": [
            {"step_key": "research", "agent_id": "product-trend-researcher",
             "task": "Research customer demand"},
            {"step_key": "strategy", "agent_id": "business-strategist",
             "task": "Recommend a product", "depends_on": ["research"]},
        ],
    }


def test_background_worker_executes_dependency_ordered_specialists(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "free-compatible-test-model")
    calls = []

    def fake_generate(system_prompt, user_prompt):
        calls.append(user_prompt)
        return ({
            "status": "completed",
            "summary": f"Completed specialist report {len(calls)}",
            "evidence": ["Evidence was supplied to the model for review."],
            "blockers": [],
        }, {"provider": "test", "model": "mock"})

    monkeypatch.setattr("ai_os.agent_runtime.generate_json", fake_generate)
    with TestClient(app) as client:
        created = client.post("/company-runs", json=_run_payload())
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        first = client.post("/worker/run-once")
        assert first.status_code == 200, first.text
        assert first.json()["processed"] is True
        assert first.json()["job"]["status"] == "completed"

        middle = client.get(f"/company-runs/{run_id}").json()
        assert middle["steps"][0]["status"] == "completed"
        assert middle["steps"][1]["status"] == "pending"

        second = client.post("/worker/run-once")
        assert second.status_code == 200, second.text
        assert second.json()["processed"] is True
        assert second.json()["job"]["status"] == "completed"

        final = client.get(f"/company-runs/{run_id}").json()

    assert len(calls) == 2
    assert final["status"] == "completed"
    assert [step["status"] for step in final["steps"]] == ["completed", "completed"]
    assert all(step["report"]["reported_to"] == "company-orchestrator" for step in final["steps"])
    assert all(step["work_packet"]["api_called"] is False for step in final["steps"])
