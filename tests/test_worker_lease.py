def test_worker_discards_result_when_lease_is_lost(monkeypatch):
    from ai_os import worker

    calls = {"finish": 0, "handler": 0}

    class FakeEvent:
        def set(self):
            pass

        def wait(self, _seconds):
            return False

    class FakeThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

        def join(self, timeout=None):
            pass

    job = {
        "id": "job-lease-lost",
        "job_type": "build_work_packet",
        "payload": {"agent_id": "researcher", "task": "test"},
    }

    monkeypatch.setattr(worker, "Event", FakeEvent)
    monkeypatch.setattr(worker, "Thread", FakeThread)
    monkeypatch.setattr(worker, "claim_next_job", lambda worker_id: job)
    monkeypatch.setattr(worker, "renew_job_lease", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        worker, "finish_job",
        lambda *args, **kwargs: calls.update(finish=calls["finish"] + 1),
    )
    monkeypatch.setitem(
        worker.HANDLERS,
        "build_work_packet",
        lambda payload: calls.update(handler=calls["handler"] + 1) or {"ok": True},
    )

    result = worker.run_once("worker-a")

    assert calls["handler"] == 1
    assert calls["finish"] == 0
    assert result["processed"] is False
    assert result["job"] is None
    assert "lost its job lease" in result["notice"]


def test_worker_does_not_report_success_if_finish_rejects_ownership(monkeypatch):
    from ai_os import worker

    class FakeEvent:
        def set(self):
            pass

        def wait(self, _seconds):
            return True

    class FakeThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    job = {
        "id": "job-owner-changed",
        "job_type": "build_work_packet",
        "payload": {"agent_id": "researcher", "task": "test"},
    }
    monkeypatch.setattr(worker, "Event", FakeEvent)
    monkeypatch.setattr(worker, "Thread", FakeThread)
    monkeypatch.setattr(worker, "claim_next_job", lambda worker_id: job)
    monkeypatch.setattr(worker, "finish_job", lambda *args, **kwargs: None)
    monkeypatch.setitem(worker.HANDLERS, "build_work_packet", lambda payload: {"ok": True})

    result = worker.run_once("worker-a")

    assert result["processed"] is False
    assert result["job"] is None
    assert "no longer owns this job" in result["notice"]
