from ai_os import agent_runtime, worker


def test_scheduler_queues_manager_review_only_after_all_delegated_steps_are_terminal(monkeypatch):
    monkeypatch.setattr(agent_runtime, "get_model_status", lambda: {"enabled": True})
    monkeypatch.setattr(agent_runtime, "list_company_runs", lambda limit=200: [{"id": "run-1"}])
    monkeypatch.setattr(agent_runtime, "propagate_blocked_steps", lambda run_id: 0)
    monkeypatch.setattr(agent_runtime, "get_company_run", lambda run_id: {
        "id": run_id,
        "steps": [
            {"step_key": "manager_task_a", "status": "completed"},
            {"step_key": "manager_task_b", "status": "blocked"},
        ],
    })
    monkeypatch.setattr(agent_runtime, "list_department_plans", lambda run_id: [
        {"status": "delegated", "department_id": "research",
         "manager_agent_id": "research-synthesist",
         "plan": {"tasks": [{"step_key": "manager_task_a"}, {"step_key": "manager_task_b"}]}},
        {"status": "delegated", "department_id": "marketing",
         "manager_agent_id": "marketing-growth-hacker",
         "plan": {"tasks": [{"step_key": "still_running"}]}},
    ])
    queued = []

    def fake_enqueue(payload):
        queued.append(payload)
        return {"id": "job-review-1"}

    monkeypatch.setattr(agent_runtime, "enqueue_job", fake_enqueue)

    result = agent_runtime.schedule_ready_steps()

    assert result["manager_reviews_scheduled"] == 1
    assert result["manager_reviews"][0]["department_id"] == "research"
    assert queued[0].job_type == "review_department_plan"
    assert queued[0].idempotency_key == "department-review:run-1:research"


def test_worker_dispatches_manager_review_through_review_service(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "review_department_plan", lambda run_id, department_id: (
        calls.append((run_id, department_id)) or {"status": "reviewed"}
    ))

    result = worker._review_department_plan({
        "run_id": "run-2", "department_id": "product",
    })

    assert result == {"status": "reviewed"}
    assert calls == [("run-2", "product")]


def test_worker_rejects_malformed_manager_review_job():
    import pytest

    with pytest.raises(ValueError, match="requires run_id and department_id"):
        worker._review_department_plan({"run_id": "run-3"})
