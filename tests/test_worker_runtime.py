import sqlite3

from ai_os.model_adapter import get_model_status
from ai_os.worker import run_once
from ai_os.worker_service import run_worker_loop
from ai_os.db import initialize_database


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


def _prepare_database(monkeypatch, tmp_path):
    database = tmp_path / "worker-test.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    with sqlite3.connect(database) as db:
        db.execute(
            """INSERT INTO tasks
               (id, title, description, department, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("task-1", "Test task", "Verify persistence", "research", "queued",
             "2026-01-01T00:00:00+00:00"),
        )
    return database


def test_worker_processes_and_persists_queued_task(monkeypatch, tmp_path):
    database = _prepare_database(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("ai_os.worker.generate_text", lambda prompt: calls.append(prompt) or "verified result")

    result = run_once(worker_id="integration-worker")

    assert result == {"processed": True, "task_id": "task-1", "status": "completed"}
    assert len(calls) == 1
    assert "Test task" in calls[0]
    with sqlite3.connect(database) as db:
        row = db.execute(
            "SELECT status, worker_id, result, error, started_at, finished_at FROM tasks WHERE id=?",
            ("task-1",),
        ).fetchone()
    assert row[0] == "completed"
    assert row[1] == "integration-worker"
    assert row[2] == "verified result"
    assert row[3] is None
    assert row[4] is not None
    assert row[5] is not None


def test_worker_persists_provider_failure_without_retry(monkeypatch, tmp_path):
    database = _prepare_database(monkeypatch, tmp_path)

    def fail(_prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("ai_os.worker.generate_text", fail)
    try:
        run_once(worker_id="failure-worker")
    except RuntimeError as exc:
        assert "provider unavailable" in str(exc)
    else:
        raise AssertionError("Expected provider failure to be raised")

    with sqlite3.connect(database) as db:
        row = db.execute(
            "SELECT status, worker_id, error, finished_at FROM tasks WHERE id=?",
            ("task-1",),
        ).fetchone()
    assert row[0] == "failed"
    assert row[1] == "failure-worker"
    assert "provider unavailable" in row[2]
    assert row[3] is not None


def test_worker_blocks_expired_lease_without_reprocessing(monkeypatch, tmp_path):
    database = _prepare_database(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("ai_os.worker.generate_text", lambda prompt: calls.append(prompt) or "unexpected")
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE tasks SET status='running', worker_id=?, started_at=?, lease_expires_at=? WHERE id=?",
            ("crashed-worker", "2026-01-01T00:00:00+00:00",
             "2026-01-01T00:01:00+00:00", "task-1"),
        )

    result = run_once(worker_id="recovery-worker")

    assert result == {"processed": False}
    assert calls == []
    with sqlite3.connect(database) as db:
        row = db.execute(
            "SELECT status, error, lease_expires_at FROM tasks WHERE id=?",
            ("task-1",),
        ).fetchone()
    assert row[0] == "blocked"
    assert "manual review required" in row[1]
    assert row[2] is None


def test_worker_blocks_legacy_stale_running_task(monkeypatch, tmp_path):
    database = _prepare_database(monkeypatch, tmp_path)
    monkeypatch.setattr("ai_os.worker.generate_text", lambda _prompt: "unexpected")
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE tasks SET status='running', worker_id=?, started_at=?, lease_expires_at=NULL WHERE id=?",
            ("old-worker", "2026-01-01T00:00:00+00:00", "task-1"),
        )

    result = run_once(worker_id="recovery-worker")

    assert result == {"processed": False}
    with sqlite3.connect(database) as db:
        row = db.execute("SELECT status FROM tasks WHERE id=?", ("task-1",)).fetchone()
    assert row[0] == "blocked"
