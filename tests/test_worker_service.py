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
    assert calls["sleep"] == [2, 2]
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



def test_worker_heartbeat_dispatch_uses_local_store_when_remote_is_not_configured(monkeypatch):
    from ai_os.worker_service import heartbeat_dispatch

    calls = []
    monkeypatch.delenv("AI_OS_CONTROL_PLANE_URL", raising=False)
    monkeypatch.delenv("AI_OS_RUNTIME_ID", raising=False)
    monkeypatch.delenv("AI_OS_RUNTIME_TOKEN", raising=False)
    monkeypatch.setattr("ai_os.worker_service.heartbeat_worker",
                        lambda *args: calls.append(args))

    heartbeat_dispatch("local-worker", "idle", None)

    assert calls == [("local-worker", "idle", None)]


def test_worker_heartbeat_dispatch_sends_authenticated_remote_heartbeat(monkeypatch):
    import json
    from ai_os.worker_service import heartbeat_dispatch

    local_calls, requests = [], []

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setenv("AI_OS_CONTROL_PLANE_URL", "https://control.example")
    monkeypatch.setenv("AI_OS_RUNTIME_ID", "runtime-123")
    monkeypatch.setenv("AI_OS_RUNTIME_TOKEN", "runtime-token-" + "x" * 40)
    monkeypatch.setattr("ai_os.worker_service.heartbeat_worker",
                        lambda *args: local_calls.append(args))
    monkeypatch.setattr("ai_os.worker_service.urllib.request.urlopen", fake_urlopen)

    heartbeat_dispatch("local-worker", "working", "job-123")

    request, timeout = requests[0]
    assert local_calls == [("local-worker", "working", "job-123")]
    assert request.full_url == "https://control.example/control-plane/runtime-heartbeat"
    assert request.get_header("X-ai-runtime-token") == "runtime-token-" + "x" * 40
    assert json.loads(request.data) == {
        "runtime_id": "runtime-123", "status": "working", "current_job_id": "job-123"
    }
    assert timeout == 10


def test_worker_heartbeat_dispatch_rejects_partial_remote_configuration(monkeypatch):
    import pytest
    from ai_os.worker_service import heartbeat_dispatch

    monkeypatch.setenv("AI_OS_CONTROL_PLANE_URL", "https://control.example")
    monkeypatch.setenv("AI_OS_RUNTIME_ID", "runtime-123")
    monkeypatch.delenv("AI_OS_RUNTIME_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="must be configured together"):
        heartbeat_dispatch("local-worker", "idle", None)


def test_worker_heartbeat_dispatch_rejects_insecure_remote_control_plane(monkeypatch):
    import pytest
    from ai_os.worker_service import heartbeat_dispatch

    monkeypatch.setenv("AI_OS_CONTROL_PLANE_URL", "http://control.example")
    monkeypatch.setenv("AI_OS_RUNTIME_ID", "runtime-123")
    monkeypatch.setenv("AI_OS_RUNTIME_TOKEN", "runtime-token-" + "x" * 40)

    with pytest.raises(RuntimeError, match="must use HTTPS"):
        heartbeat_dispatch("local-worker", "idle", None)
