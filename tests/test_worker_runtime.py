from ai_os.model_adapter import get_model_status
from ai_os.worker_service import run_worker_loop


def test_worker_loop_schedules_and_processes(monkeypatch):
    calls = {"schedule": 0, "run": 0, "sleep": 0}
    stopped = {"value": False}

    def schedule():
        calls["schedule"] += 1
        return {"scheduled": 0}

    def run(*, worker_id):
        calls["run"] += 1
        stopped["value"] = True
        return {"processed": False}

    def sleep(_):
        calls["sleep"] += 1

    run_worker_loop(
        worker_id="test-worker",
        poll_seconds=1,
        stop_requested=lambda: stopped["value"],
        sleep=sleep,
        schedule=schedule,
        run=run,
    )
    assert calls["schedule"] == 1
    assert calls["run"] == 1


def test_model_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    assert get_model_status()["enabled"] is False
