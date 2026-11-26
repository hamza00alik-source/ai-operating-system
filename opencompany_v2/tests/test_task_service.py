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



def test_agent_worker_reuses_persisted_result_after_ack_failure(tmp_path):
    from opencompany.agent import AgentProfile
    from opencompany.permissions import Action
    from opencompany.skills import Skill, SkillRegistry
    from opencompany.worker import AgentWorker

    store = Store(str(tmp_path / "agent-recovery.db"))
    service = TaskService(store)
    queue = ExecutionQueue(store.db, store.lock)
    profile = AgentProfile(
        role_key="researcher", mission="Research assigned tasks",
        capabilities=("research",), agent_id="agent-recovery",
    )
    store.save_agent_profile(profile)

    calls = []
    registry = SkillRegistry()
    registry.register(
        Skill("research", "Research", "Perform bounded research",
              (Action.RESEARCH.value,), (), required_capabilities=("research",)),
        lambda payload: calls.append(payload) or {
            "status": "completed", "summary": "recovered result",
            "artifacts": [], "steps_used": 1,
        },
    )
    store.assign_skill(profile.agent_id, registry._skills["research"][0])

    task = service.create("Agent crash recovery", "Do not execute the handler twice")
    service.move(task.id, TaskStatus.READY, actor="test")
    service.assign_to_agent(task.id, profile.agent_id, "research")
    job_id = service.enqueue_assigned(task.id, queue)

    original_complete = queue.complete
    complete_calls = []

    def fail_first_ack(job, worker, result, attempt):
        complete_calls.append(attempt)
        if len(complete_calls) == 1:
            return False
        return original_complete(job, worker, result, attempt)

    queue.complete = fail_first_ack
    worker = AgentWorker(
        profile.agent_id, store, queue, registry, {"research": Action.RESEARCH.value},
        task_service=service,
    )

    with pytest.raises(RuntimeError, match="lease was lost"):
        worker.run_once()

    assert queue.get(job_id)["state"] == "queued"
    assert len(calls) == 1

    recovered = worker.run_once()
    assert recovered["status"] == "completed"
    assert queue.get(job_id)["state"] == "completed"
    persisted = next(item for item in store.list_tasks() if item["id"] == str(task.id))
    assert persisted["status"] == TaskStatus.COMPLETED.value
    assert len(calls) == 1
    assert complete_calls == [1, 2]
    store.close()
