import threading

from ai_os import worker_service


def test_worker_loop_processes_both_existing_queues(monkeypatch):
    calls = []
    stop = threading.Event()

    def discovery():
        calls.append('discovery')
        return True

    def agent():
        calls.append('agent')
        stop.set()
        return True

    monkeypatch.setattr(worker_service, 'run_discovery_once', discovery)
    monkeypatch.setattr(worker_service, 'run_agent_once', agent)
    worker_service.run_worker_loop(worker_id='test-worker', stop_event=stop, poll_seconds=2)
    assert calls == ['discovery', 'agent']


def test_worker_loop_recovers_from_transient_queue_error(monkeypatch):
    calls = []
    stop = threading.Event()

    def discovery():
        calls.append('discovery')
        if len(calls) == 1:
            raise RuntimeError('temporary')
        stop.set()
        return True

    monkeypatch.setattr(worker_service, 'run_discovery_once', discovery)
    monkeypatch.setattr(worker_service, 'run_agent_once', lambda: False)
    monkeypatch.setattr(stop, 'wait', lambda _seconds: None)
    worker_service.run_worker_loop(worker_id='test-worker', stop_event=stop, poll_seconds=2)
    assert len(calls) == 2
