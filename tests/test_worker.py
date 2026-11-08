from datetime import datetime, timedelta, timezone

from ai_os.agent_runtime import schedule_ready_steps
from ai_os.db import connect, initialize_database
from ai_os.schemas import TaskCreate
from ai_os.service import create_task
from ai_os import worker


def setup_worker_db(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'worker-test.db'}")
    initialize_database()


def test_worker_claims_task_and_persists_model_result(monkeypatch, tmp_path):
    setup_worker_db(monkeypatch, tmp_path)
    task = create_task(TaskCreate(title="Research a market", department="research"))
    monkeypatch.setattr(
        worker,
        "chat_completion",
        lambda prompt: {
            "provider": "test",
            "model": "fake-model",
            "response": "Research summary",
            "latency_ms": 12,
            "usage": None,
        },
    )

    result = worker.run_once(worker_id="worker-test")
    assert result["processed"] is True
    assert result["status"] == "completed"
    with connect() as db:
        saved = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
    assert saved["status"] == "completed"
    assert saved["result"] == "Research summary"
    assert saved["attempts"] == 1
    assert saved["worker_id"] is None
    assert worker.run_once(worker_id="worker-test")["reason"] == "queue_empty"


def test_worker_requeues_transient_model_failure(monkeypatch, tmp_path):
    setup_worker_db(monkeypatch, tmp_path)
    task = create_task(TaskCreate(title="Retry this task"))
    monkeypatch.setattr(
        worker,
        "chat_completion",
        lambda prompt: (_ for _ in ()).throw(worker.ModelAdapterError("temporary provider error")),
    )
    result = worker.run_once(worker_id="worker-test")
    assert result["status"] == "queued"
    with connect() as db:
        saved = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
    assert saved["status"] == "queued"
    assert saved["attempts"] == 1
    assert saved["error"] == "temporary provider error"


def test_scheduler_recovers_expired_worker_lease(monkeypatch, tmp_path):
    setup_worker_db(monkeypatch, tmp_path)
    task = create_task(TaskCreate(title="Recover after restart"))
    expired = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    with connect() as db:
        db.execute(
            """UPDATE tasks SET status='running', worker_id='dead-worker',
               lease_expires_at=?, attempts=1 WHERE id=?""",
            (expired, task["id"]),
        )
    result = schedule_ready_steps()
    assert result["recovered"] == 1
    with connect() as db:
        saved = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
    assert saved["status"] == "queued"
    assert saved["worker_id"] is None
    assert saved["lease_expires_at"] is None


def test_scheduler_fails_task_after_retry_limit(monkeypatch, tmp_path):
    setup_worker_db(monkeypatch, tmp_path)
    task = create_task(TaskCreate(title="Exhausted task"))
    expired = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    with connect() as db:
        db.execute(
            """UPDATE tasks SET status='running', worker_id='dead-worker',
               lease_expires_at=?, attempts=3, max_attempts=3 WHERE id=?""",
            (expired, task["id"]),
        )
    result = schedule_ready_steps()
    assert result["failed"] == 1
    with connect() as db:
        saved = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
    assert saved["status"] == "failed"
    assert saved["completed_at"] is not None
