from threading import Event

from ai_os.worker_service import run_worker_loop


def test_worker_loop_uses_bounded_poll_and_stops_cleanly():
    stop = Event()
    calls = []

    def fake_run(*, worker_id):
        calls.append(worker_id)
        return {"processed": False}

    def fake_sleep(seconds):
        assert seconds == 2
        stop.set()

    run_worker_loop(
        worker_id="test-worker",
        poll_seconds=2,
        stop_requested=stop.is_set,
        sleep=fake_sleep,
        run=fake_run,
    )
    assert calls == ["test-worker"]


def test_worker_loop_applies_exponential_backoff_after_errors():
    stop = Event()
    errors = []
    delays = []

    def broken_run(*, worker_id):
        raise RuntimeError("temporary database failure")

    def fake_sleep(seconds):
        delays.append(seconds)
        stop.set()

    run_worker_loop(
        worker_id="test-worker",
        poll_seconds=3,
        stop_requested=stop.is_set,
        sleep=fake_sleep,
        run=broken_run,
        on_error=lambda exc, delay: errors.append((str(exc), delay)),
    )
    assert errors == [("temporary database failure", 3)]
    assert delays == [3]
