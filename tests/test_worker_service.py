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


def test_worker_loop_refreshes_runtime_heartbeat_during_long_job():
    from threading import Event

    keepalive_seen = Event()
    stop = {"value": False}
    heartbeats = []

    def heartbeat(worker_id, status, current_job_id):
        heartbeats.append((status, current_job_id))
        if sum(1 for item in heartbeats if item[0] == "working") >= 2:
            keepalive_seen.set()

    def run(*, worker_id):
        assert keepalive_seen.wait(1), "worker did not send a keepalive during execution"
        stop["value"] = True
        return {"processed": False}

    run_worker_loop(
        worker_id="long-job-worker",
        poll_seconds=1,
        stop_requested=lambda: stop["value"],
        sleep=lambda seconds: None,
        schedule=lambda: {"scheduled": 0},
        run=run,
        heartbeat=heartbeat,
        heartbeat_interval_seconds=0.05,
    )

    assert sum(1 for item in heartbeats if item[0] == "working") >= 2



def test_worker_does_not_retry_model_job_after_quota_limit(monkeypatch):
    from ai_os.worker import run_once
    from ai_os.model_adapter import ModelQuotaExceeded
    from ai_os import worker

    claimed = {
        "id": "quota-job", "job_type": "execute_company_step",
        "payload": {"run_id": "run-1", "step_key": "research"},
    }
    monkeypatch.setattr(worker, "claim_next_job", lambda worker_id: claimed)
    monkeypatch.setattr(worker, "renew_job_lease", lambda *args, **kwargs: True)
    monkeypatch.setattr(worker, "execute_company_step",
                        lambda payload: (_ for _ in ()).throw(ModelQuotaExceeded("quota reached")))
    failures = []
    monkeypatch.setattr(worker, "fail_job",
                        lambda job_id, worker_id, error, retry=True: failures.append(retry) or {
                            "status": "failed", "error": error
                        })
    blocked = []
    monkeypatch.setattr(worker, "mark_company_step_blocked",
                        lambda *args: blocked.append(args))
    result = run_once(worker_id="worker-test")
    assert failures == [False]
    assert result["job"]["status"] == "failed"
    assert blocked and "quota reached" in blocked[0][2]
