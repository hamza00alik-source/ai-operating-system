import pytest

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
