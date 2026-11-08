import pytest
from threading import Event

from ai_os import embedded_worker


def test_embedded_worker_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_OS_WORKER_EMBEDDED", raising=False)
    assert embedded_worker.start_embedded_worker() is None


def test_embedded_worker_requires_explicit_live_model_configuration(monkeypatch):
    monkeypatch.setenv("AI_OS_WORKER_EMBEDDED", "true")
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    monkeypatch.delenv("AI_OS_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("AI_OS_MODEL_NAME", raising=False)
    with pytest.raises(RuntimeError, match="AI_OS_WORKER_EMBEDDED"):
        embedded_worker.start_embedded_worker()


def test_embedded_worker_starts_supervised_loop_and_stops(monkeypatch):
    monkeypatch.setenv("AI_OS_WORKER_EMBEDDED", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "test-model")
    observed = {}
    started = Event()

    def fake_loop(**kwargs):
        observed.update(kwargs)
        started.set()

    monkeypatch.setattr(embedded_worker, "run_worker_loop", fake_loop)
    stop = embedded_worker.start_embedded_worker()
    assert callable(stop)
    assert started.wait(2), "embedded worker thread did not start"
    assert observed["poll_seconds"] == 3
    assert observed["worker_id"].startswith("embedded-agent-worker-")
    assert callable(observed["stop_requested"])
    assert callable(observed["sleep"])
    stop()
    assert observed["stop_requested"]() is True
