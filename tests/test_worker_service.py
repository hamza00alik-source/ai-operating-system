from ai_os.worker_service import run_worker_loop


def test_worker_loop_recovers_after_transient_scheduler_failure():
    calls = {"schedule": 0, "run": 0, "sleep": [], "errors": []}
    stop = {"value": False}

    def schedule():
        calls["schedule"] += 1
        if calls["schedule"] == 1:
            raise OSError("temporary database interruption")
        return {"scheduled": 0}

    def run(*, worker_id):
        calls["run"] += 1
        stop["value"] = True
        return {"processed": False}

    run_worker_loop(
        worker_id="test-worker",
        poll_seconds=2,
        stop_requested=lambda: stop["value"],
        sleep=lambda seconds: calls["sleep"].append(seconds),
        schedule=schedule,
        run=run,
        on_error=lambda exc, delay: calls["errors"].append((type(exc).__name__, delay)),
    )

    assert calls["errors"] == [("OSError", 2)]
    assert calls["sleep"] == [2]
    assert calls["schedule"] == 2
    assert calls["run"] == 1


def test_worker_loop_uses_bounded_exponential_backoff():
    calls = {"errors": [], "sleep": []}
    attempts = {"count": 0}

    def schedule():
        attempts["count"] += 1
        raise RuntimeError("temporary")

    def stop():
        return attempts["count"] >= 4

    run_worker_loop(
        worker_id="test-worker",
        poll_seconds=3,
        stop_requested=stop,
        sleep=lambda seconds: calls["sleep"].append(seconds),
        schedule=schedule,
        on_error=lambda exc, delay: calls["errors"].append(delay),
    )

    assert calls["errors"] == [3, 6, 12, 24]
    assert calls["sleep"] == [3, 6, 12]
