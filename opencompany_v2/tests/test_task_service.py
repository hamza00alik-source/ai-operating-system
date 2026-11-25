import json

import pytest
from opencompany.queue import ExecutionQueue

from opencompany.domain import TaskStatus
from opencompany.store import Store
from opencompany.task_service import TaskService


def test_move_updates_state_attempts_and_event_atomically(tmp_path):
    store = Store(str(tmp_path / "tasks.db"))
    service = TaskService(store)
    task = service.create("Lifecycle test", "Verify atomic task transitions")

    ready = service.move(task.id, TaskStatus.READY, actor="test")
    running = service.move(task.id, TaskStatus.RUNNING, actor="worker")

    assert ready["status"] == TaskStatus.READY.value
    assert running["status"] == TaskStatus.RUNNING.value
    assert running["attempts"] == 1
    persisted = next(item for item in store.list_tasks() if item["id"] == str(task.id))
    assert persisted["status"] == TaskStatus.RUNNING.value
    assert persisted["attempts"] == 1
    assert store.verify_event_chain()
    store.close()


def test_illegal_move_leaves_task_and_event_ledger_unchanged(tmp_path):
    store = Store(str(tmp_path / "tasks.db"))
    service = TaskService(store)
    task = service.create("Invalid transition", "Ensure rejected transitions do not mutate state")
    before_events = store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    with pytest.raises(ValueError, match="Illegal task transition"):
        service.move(task.id, TaskStatus.RUNNING, actor="test")

    persisted = next(item for item in store.list_tasks() if item["id"] == str(task.id))
    after_events = store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert persisted["status"] == TaskStatus.DISCOVERED.value
    assert persisted["attempts"] == 0
    assert after_events == before_events
    assert store.verify_event_chain()
    store.close()



def test_reconcile_completed_job_repairs_task_after_worker_crash(tmp_path):
    store = Store(str(tmp_path / "recovery.db"))
    service = TaskService(store)
    queue = ExecutionQueue(store.db, store.lock)
    task = service.create("Crash recovery", "Recover acknowledged execution")
    service.move(task.id, TaskStatus.READY, actor="test")
    service.move(task.id, TaskStatus.RUNNING, actor="worker")

    row = store.db.execute("SELECT payload FROM tasks WHERE id=?", (str(task.id),)).fetchone()
    payload = json.loads(row["payload"])
    payload["assigned_agent_id"] = "agent-1"
    store.db.execute("UPDATE tasks SET payload=? WHERE id=?",
                     (json.dumps(payload, sort_keys=True), str(task.id)))
    store.db.commit()

    job_id = queue.enqueue(str(task.id), {"task_id": str(task.id), "agent_id": "agent-1"})
    lease = queue.claim("agent-worker:agent-1", agent_id="agent-1")
    assert lease["id"] == job_id
    report = {"status": "completed", "summary": "saved", "artifacts": [], "steps_used": 1}
    service.record_result(task.id, "agent-1", job_id, report)
    assert queue.complete(job_id, "agent-worker:agent-1", report, lease["attempts"])

    # Simulate the crash window: queue is completed, task is still RUNNING.
    reconciled = service.reconcile_completed_jobs(queue)
    assert reconciled == [str(task.id)]
    persisted = next(item for item in store.list_tasks() if item["id"] == str(task.id))
    assert persisted["status"] == TaskStatus.COMPLETED.value
    assert service.reconcile_completed_jobs(queue) == []
    store.close()
