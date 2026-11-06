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



def test_blocked_specialist_propagates_to_dependent_steps(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "free-compatible-test-model")

    def blocked_generate(system_prompt, user_prompt):
        return ({
            "status": "blocked",
            "summary": "Research cannot be completed with the available evidence.",
            "evidence": [],
            "blockers": ["No verifiable source data was supplied."],
        }, {"provider": "test", "model": "mock"})

    monkeypatch.setattr("ai_os.agent_runtime.generate_json", blocked_generate)
    with TestClient(app) as client:
        created = client.post("/company-runs", json=_run_payload())
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        first = client.post("/worker/run-once")
        assert first.status_code == 200, first.text
        assert first.json()["job"]["status"] == "completed"

        second = client.post("/worker/run-once")
        assert second.status_code == 200, second.text
        final = client.get(f"/company-runs/{run_id}").json()

    assert final["status"] == "blocked"
    assert [step["status"] for step in final["steps"]] == ["blocked", "blocked"]
    assert final["steps"][1]["report"]["system_generated"] is True
    assert "research" in final["steps"][1]["report"]["blockers"][0]


def test_exhausted_specialist_retries_mark_step_and_run_blocked(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "free-compatible-test-model")

    def failing_generate(system_prompt, user_prompt):
        raise RuntimeError("simulated inference outage")

    monkeypatch.setattr("ai_os.agent_runtime.generate_json", failing_generate)
    with TestClient(app) as client:
        payload = {
            "title": "Retry exhaustion test",
            "steps": [
                {"step_key": "research", "agent_id": "product-trend-researcher",
                 "task": "Research customer demand"}
            ],
        }
        created = client.post("/company-runs", json=payload)
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        results = [client.post("/worker/run-once").json() for _ in range(3)]
        final = client.get(f"/company-runs/{run_id}").json()

    assert [item["job"]["status"] for item in results] == ["queued", "queued", "failed"]
    assert final["status"] == "blocked"
    assert final["steps"][0]["status"] == "blocked"
    assert "exhausted its retry allowance" in final["steps"][0]["report"]["summary"]



def test_blocked_dependencies_reconcile_even_when_model_is_disabled(monkeypatch):
    from ai_os.agent_runtime import schedule_ready_steps
    from ai_os.execution import submit_step_report
    from ai_os.execution_schemas import StepReportCreate

    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "false")
    with TestClient(app) as client:
        created = client.post("/company-runs", json=_run_payload())
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]
        dispatched = client.post(f"/company-runs/{run_id}/steps/research/dispatch")
        assert dispatched.status_code == 200
        submit_step_report(
            run_id,
            "research",
            StepReportCreate(
                status="blocked",
                summary="Research was blocked.",
                blockers=["Missing verified evidence."],
            ),
        )

        outcome = schedule_ready_steps()
        final = client.get(f"/company-runs/{run_id}").json()

    assert outcome["model_enabled"] is False
    assert final["status"] == "blocked"
    assert [step["status"] for step in final["steps"]] == ["blocked", "blocked"]


def test_agent_creates_only_unreviewed_candidates_from_supplied_source_urls(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "free-compatible-test-model")
    source_url = "https://example.com/verified-in-task"
    def fake_generate(system_prompt, user_prompt):
        assert source_url in user_prompt
        return ({
            "status": "completed",
            "summary": "Reviewed supplied research context.",
            "evidence": ["The task included the cited source URL."],
            "blockers": [],
            "knowledge_candidates": [
                {
                    "title": "Candidate from supplied source",
                    "content": "A concise factual note for owner review.",
                    "category": "market_research",
                    "source_url": source_url,
                    "source_title": "Research supplied in task",
                    "confidence": 0.7,
                    "tags": ["market", "research"],
                },
                {
                    "title": "Unverified invented source",
                    "content": "This must not be stored.",
                    "category": "market_research",
                    "source_url": "https://invented.example/not-in-context",
                    "source_title": "Unverified",
                    "confidence": 0.9,
                    "tags": ["invented"],
                },
            ],
        }, {"provider": "test", "model": "mock"})

    monkeypatch.setattr("ai_os.agent_runtime.generate_json", fake_generate)
    with TestClient(app) as client:
        created = client.post("/company-runs", json={
            "title": "Knowledge integration test",
            "description": f"Analyze this source: {source_url}",
            "steps": [{
                "step_key": "research",
                "agent_id": "product-trend-researcher",
                "task": "Summarize the supplied source.",
            }],
        })
        assert created.status_code == 201, created.text
        result = client.post("/worker/run-once")
        assert result.status_code == 200, result.text
        assert result.json()["job"]["status"] == "completed"
        candidates = client.get("/knowledge", params={"status": "candidate"}).json()

    stored = [item for item in candidates if item["title"] == "Candidate from supplied source"]
    assert len(stored) == 1
    assert stored[0]["status"] == "candidate"
    assert stored[0]["created_by"] == "agent:product-trend-researcher"
    assert not any(item["title"] == "Unverified invented source" for item in candidates)
