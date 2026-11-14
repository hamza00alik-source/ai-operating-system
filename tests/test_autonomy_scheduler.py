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
    assert status["lease_token"] if "lease_token" in status else True
    assert status["consecutive_failures"] == 0


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


def test_expired_lease_recovers_after_scheduler_recreation():
    db = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
    first = DurableAutomationScheduler(db, lease_seconds=10)
    first.register_interval_job("recoverable", 30, lambda: None)
    db.execute(
        """UPDATE automation_jobs SET lease_token='abandoned',
           lease_expires_at=? WHERE job_id='recoverable'""",
        ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),),
    )
    calls = []
    restarted = DurableAutomationScheduler(db, lease_seconds=10)
    restarted.register_interval_job("recoverable", 30, lambda: calls.append("recovered"))

    result = restarted.run_due()

    assert result["succeeded"] == 1
    assert calls == ["recovered"]
    assert restarted.status()[0]["last_status"] == "succeeded"


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
