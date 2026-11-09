from ai_os import worker_service


class StopAfterWait:
    def __init__(self):
        self.stopped = False
        self.wait_calls = 0

    def is_set(self):
        return self.stopped

    def wait(self, _seconds):
        self.wait_calls += 1
        if self.wait_calls >= 2:
            self.stopped = True


def test_worker_loop_processes_both_existing_queues(monkeypatch):
    calls = []
    stop = StopAfterWait()

    def discovery():
        calls.append("discovery")
        return True

    def agent(*, worker_id=None):
        assert worker_id == "test-worker"
        calls.append("agent")
        stop.stopped = True
        return True

    monkeypatch.setattr(worker_service, "run_discovery_once", discovery)
    monkeypatch.setattr(worker_service, "recover_interrupted_runs", lambda: 0)
    monkeypatch.setattr(worker_service, "run_agent_once", agent)
    worker_service.run_worker_loop(worker_id="test-worker", stop_event=stop, poll_seconds=2)
    assert calls == ["discovery", "agent"]


def test_worker_loop_recovers_from_transient_queue_error(monkeypatch):
    calls = []
    stop = StopAfterWait()

    def discovery():
        calls.append("discovery")
        if len(calls) == 1:
            raise RuntimeError("temporary")
        stop.stopped = True
        return True

    monkeypatch.setattr(worker_service, "run_discovery_once", discovery)
    monkeypatch.setattr(worker_service, "recover_interrupted_runs", lambda: 0)
    monkeypatch.setattr(worker_service, "run_agent_once", lambda **_kwargs: False)
    worker_service.run_worker_loop(worker_id="test-worker", stop_event=stop, poll_seconds=2)
    assert len(calls) == 2
