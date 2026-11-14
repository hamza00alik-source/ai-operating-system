from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from opencompany_core.autonomy_scheduler import DurableAutomationScheduler


def test_due_job_runs_once_and_persists_next_run():
    db = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
    scheduler = DurableAutomationScheduler(db)
    calls = []
    scheduler.register_interval_job("safe_internal_cycle", 60, lambda: calls.append("ran"))

    result = scheduler.run_due()

    assert result == {"claimed": 1, "succeeded": 1, "failed": 0, "unregistered": 0}
    assert calls == ["ran"]
    status = scheduler.status()[0]
    assert status["last_status"] == "succeeded"
    assert status["lease_expires_at"] is None
    assert status["consecutive_failures"] == 0
    history = scheduler.history(job_id="safe_internal_cycle")
    assert len(history) == 1
    assert history[0]["status"] == "succeeded"
    assert history[0]["finished_at"] is not None


def test_job_failure_is_recorded_and_backed_off():
    db = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
    scheduler = DurableAutomationScheduler(db, max_backoff_seconds=30)

    def fail():
        raise RuntimeError("do not persist exception message")

    scheduler.register_interval_job("failing_job", 1, fail)
    result = scheduler.run_due()

    assert result["failed"] == 1
    status = scheduler.status()[0]
    assert status["last_status"] == "failed"
    assert status["last_error_code"] == "RuntimeError"
    assert status["consecutive_failures"] == 1
    assert "do not persist" not in str(status)
    assert scheduler.history()[0]["error_code"] == "RuntimeError"


def test_expired_lease_recovers_after_real_database_reopen(tmp_path):
    database_path = tmp_path / "automation.sqlite3"
    first_db = sqlite3.connect(database_path, isolation_level=None, check_same_thread=False)
    first = DurableAutomationScheduler(first_db, lease_seconds=10)
    first.register_interval_job("recoverable", 30, lambda: None)
    old_token = "abandoned-process-lease"
    old_run_id = "abandoned-process-run"
    started = datetime.now(timezone.utc).isoformat()
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    first_db.execute(
        """UPDATE automation_jobs SET lease_token=?,lease_expires_at=?,
           next_run_at=?,last_status='running' WHERE job_id='recoverable'""",
        (old_token, expired, expired),
    )
    first_db.execute(
        """INSERT INTO automation_job_runs
           (run_id,job_id,lease_token,started_at,status)
           VALUES(?,?,?,?, 'running')""",
        (old_run_id, "recoverable", old_token, started),
    )
    first_db.close()

    restarted_db = sqlite3.connect(database_path, isolation_level=None, check_same_thread=False)
    calls = []
    restarted = DurableAutomationScheduler(restarted_db, lease_seconds=10)
    restarted.register_interval_job("recoverable", 30, lambda: calls.append("recovered"))
    result = restarted.run_due()

    assert result["succeeded"] == 1
    assert calls == ["recovered"]
    history = restarted.history(job_id="recoverable")
    assert len(history) == 2
    assert {item["status"] for item in history} == {"interrupted", "succeeded"}
    assert next(item for item in history if item["run_id"] == old_run_id)["error_code"] == "lease_expired"


def test_disabled_job_does_not_run_and_invalid_limits_fail_closed():
    db = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
    scheduler = DurableAutomationScheduler(db)
    calls = []
    scheduler.register_interval_job("paused", 60, lambda: calls.append(1), enabled=False)
    assert scheduler.run_due()["claimed"] == 0
    assert calls == []
    assert scheduler.set_enabled("paused", True) is True
    assert scheduler.run_due()["succeeded"] == 1
    with pytest.raises(ValueError):
        scheduler.run_due(limit=0)
    with pytest.raises(ValueError):
        scheduler.history(limit=501)
