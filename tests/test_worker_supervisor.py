from threading import Event
from uuid import uuid4

import pytest

from opencompany_core.worker_supervisor import (
    WorkerSupervisor,
    WorkerSupervisorError,
)


class SequenceWorker:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0

    def run_once(self, agent_id, role_key):
        self.calls += 1
        value = next(self.results)
        if isinstance(value, Exception):
            raise value
        return value


def test_supervisor_counts_cycles_and_stops_at_cycle_limit():
    worker = SequenceWorker(["completed_review_required", "idle"])
    supervisor = WorkerSupervisor(
        worker, uuid4(), "operations_manager", idle_poll_seconds=0.1,
    )
    result = supervisor.run(Event(), cycle_limit=2)
    assert result.completed == 1
    assert result.idle_cycles == 1
    assert result.failed_cycles == 0
    assert result.stopped is False
    assert worker.calls == 2


def test_supervisor_stops_after_consecutive_failure_limit():
    worker = SequenceWorker([RuntimeError("secret detail"), RuntimeError("secret detail")])
    supervisor = WorkerSupervisor(
        worker, uuid4(), "operations_manager",
        failure_backoff_seconds=0.1, max_consecutive_failures=2,
    )
    with pytest.raises(WorkerSupervisorError, match="failure limit"):
        supervisor.run(Event())
    assert worker.calls == 2


def test_supervisor_rejects_unbounded_configuration():
    with pytest.raises(ValueError):
        WorkerSupervisor(SequenceWorker([]), uuid4(), "operations_manager",
                         idle_poll_seconds=0)
    with pytest.raises(ValueError):
        WorkerSupervisor(SequenceWorker([]), uuid4(), "operations_manager",
                         max_consecutive_failures=0)
    with pytest.raises(ValueError):
        WorkerSupervisor(SequenceWorker([]), uuid4(), "operations_manager").run(
            Event(), cycle_limit=0
        )
