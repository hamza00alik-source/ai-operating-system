from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from time import sleep
from uuid import uuid4

import pytest

from opencompany_core.domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.execution import AgentDeliverable
from opencompany_core.persistence import SQLiteStore
from opencompany_core.worker_queue import DurableWorkerQueue
from opencompany_core.worker_runner import OpenCompanyWorker, WorkerConfigurationError


class FakeExecutor:
    def execute(self, role_key, item, **kwargs):
        assert item.state == TaskState.IN_PROGRESS
        return AgentDeliverable(
            id=uuid4(), work_item_id=item.id, role_key=role_key,
            content="Draft for review", provider="fake", model="deterministic",
            cost_usd=0.0,
        )


class MemorySink:
    def __init__(self):
        self.items = {}

    def save(self, deliverable):
        self.items[deliverable.id] = deliverable


class FailOnceSink(MemorySink):
    def __init__(self):
        super().__init__()
        self.failed = False

    def save(self, deliverable):
        if not self.failed:
            self.failed = True
            raise OSError("temporary sink failure")
        super().save(deliverable)


def setup(tmp_path, *, agent_state=AgentState.ACTIVE, agent_team_key="management", queue_max_attempts=3):
    agent_id = uuid4()
    item = WorkItem(
        id=uuid4(), title="Test task", objective="Produce a draft",
        department="revenue-partnerships", state=TaskState.IN_PROGRESS,
        assigned_agent_id=agent_id,
    )
    store = SQLiteStore(tmp_path / "core.sqlite3")
    store.save_work_item(item)
    store.save_agent(AgentProfile(
        id=agent_id, name="Marketplace Operations Manager",
        department="revenue-partnerships", purpose="Coordinate marketplace work",
        capabilities=("marketplace_research",), state=agent_state,
        role_key="marketplace_operations_analyst", team_key=agent_team_key,
    ))
    queue = DurableWorkerQueue(tmp_path / "queue.sqlite3", max_attempts=queue_max_attempts)
    queue.enqueue(item.id, agent_id, {"source": "test"})
    return agent_id, item, store, queue


def test_worker_saves_review_required_artifact_then_completes(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    sink = MemorySink()
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), sink)
    assert worker.run_once(agent, "marketplace_operations_analyst") == "completed_review_required"
    assert len(sink.items) == 1
    artifact = next(iter(sink.items.values()))
    assert artifact.review_required is True
    assert queue.counts() == {"done": 1}
    assert store.get_work_item(item.id).state == TaskState.REVIEW
    saved = store.list_deliverables(item.id)
    assert len(saved) == 1
    assert saved[0]["content"] == "Draft for review"
    assert saved[0]["review_required"] is True
    assert store.audit_event_count() == 1
    assert store.verify_audit_chain()
    queue.close()
    store.close()


def test_worker_requires_durable_sink(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    with pytest.raises(WorkerConfigurationError):
        OpenCompanyWorker(queue, store, FakeExecutor(), None)
    queue.close()
    store.close()


def test_worker_rejects_draft_agent_profile(tmp_path):
    agent, item, store, queue = setup(tmp_path, agent_state=AgentState.DRAFT)
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), MemorySink())
    with pytest.raises(WorkerConfigurationError, match="not active"):
        worker.run_once(agent, "marketplace_operations_analyst")
    assert queue.counts() == {"queued": 1}
    queue.close()
    store.close()


def test_worker_rejects_role_not_bound_to_agent_profile(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), MemorySink())
    with pytest.raises(WorkerConfigurationError, match="role does not match"):
        worker.run_once(agent, "risk_and_quality_reviewer")
    assert queue.counts() == {"queued": 1}
    queue.close()
    store.close()


def test_worker_rejects_profile_with_wrong_team_identity(tmp_path):
    agent, item, store, queue = setup(tmp_path, agent_team_key="finance-risk__team_1")
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), MemorySink())
    with pytest.raises(WorkerConfigurationError, match="team does not match"):
        worker.run_once(agent, "marketplace_operations_analyst")
    assert queue.counts() == {"queued": 1}
    queue.close()
    store.close()


def test_worker_rejects_wrong_agent_assignment(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    other = uuid4()
    queue.close()
    queue = DurableWorkerQueue(tmp_path / "wrong-agent-queue.sqlite3")
    queue.enqueue(item.id, other, {})
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), MemorySink())
    with pytest.raises(WorkerConfigurationError, match="assignment"):
        worker.run_once(other, "marketplace_operations_analyst")
    assert queue.counts() == {"queued": 1}
    queue.close()
    store.close()


def test_worker_retry_uses_stable_artifact_id_after_sink_failure(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    sink = FailOnceSink()
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), sink)
    with pytest.raises(OSError, match="temporary sink failure"):
        worker.run_once(agent, "marketplace_operations_analyst")
    assert queue.counts() == {"queued": 1}
    assert worker.run_once(agent, "marketplace_operations_analyst") == "completed_review_required"
    assert len(sink.items) == 1
    assert queue.counts() == {"done": 1}
    assert store.audit_event_count() == 2
    assert store.verify_audit_chain()
    queue.close()
    store.close()


@pytest.mark.parametrize("budget", [float("nan"), float("inf"), float("-inf"), -0.01])
def test_worker_rejects_invalid_request_budget(tmp_path, budget):
    agent, item, store, queue = setup(tmp_path)
    with pytest.raises(ValueError, match="finite"):
        OpenCompanyWorker(queue, store, FakeExecutor(), MemorySink(),
                          request_budget_usd=budget)
    queue.close()
    store.close()


def test_worker_recovers_queue_ack_after_artifact_was_durably_saved(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    deliverable = AgentDeliverable(
        id=uuid4(), work_item_id=item.id, role_key="marketplace_operations_analyst",
        content="Already persisted draft", provider="fake", model="deterministic", cost_usd=0.0,
    )
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="agent",
        actor_id=str(agent), action="worker.deliverable_saved", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id="recovery-test",
        details={"role_key": deliverable.role_key},
    )
    assert store.save_deliverable_with_audit(deliverable, event) is True
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), MemorySink())
    assert worker.run_once(agent, "marketplace_operations_analyst") == "completed_review_required"
    assert queue.counts() == {"done": 1}
    assert len(store.list_deliverables(item.id)) == 1
    queue.close()
    store.close()


class AlwaysFailSink(MemorySink):
    def save(self, deliverable):
        raise OSError("permanent sink failure")


def test_exhausted_queue_retries_mark_work_item_failed(tmp_path):
    agent, item, store, queue = setup(tmp_path, queue_max_attempts=1)
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), AlwaysFailSink())
    with pytest.raises(OSError, match="permanent sink failure"):
        worker.run_once(agent, "marketplace_operations_analyst")
    assert queue.counts() == {"dead": 1}
    assert store.get_work_item(item.id).state == TaskState.FAILED
    assert store.verify_audit_chain()
    queue.close()
    store.close()


def test_deliverable_write_and_review_transition_roll_back_together(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    duplicate_event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="test.duplicate", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id="atomic-test",
    )
    store.append_audit_record(duplicate_event)
    deliverable = AgentDeliverable(
        id=uuid4(), work_item_id=item.id, role_key="marketplace_operations_analyst",
        content="Draft", provider="fake", model="deterministic", cost_usd=0.0,
    )
    with pytest.raises(Exception):
        store.save_deliverable_with_audit(deliverable, duplicate_event)
    assert store.get_work_item(item.id).state == TaskState.IN_PROGRESS
    assert store.list_deliverables(item.id) == ()
    assert store.verify_audit_chain()
    queue.close()
    store.close()


def test_worker_heartbeats_long_running_execution_before_lease_expiry(tmp_path):
    agent, item, store, queue = setup(tmp_path)
    queue.lease_seconds = 0.3  # Short test lease; production values remain validated.
    started = Event()

    class SlowExecutor(FakeExecutor):
        def execute(self, role_key, work_item, **kwargs):
            started.set()
            sleep(0.55)
            return super().execute(role_key, work_item, **kwargs)

    worker = OpenCompanyWorker(queue, store, SlowExecutor(), MemorySink())
    results = []
    errors = []

    def run():
        try:
            results.append(worker.run_once(agent, "marketplace_operations_analyst"))
        except Exception as exc:
            errors.append(exc)

    began = datetime.now(timezone.utc)
    thread = Thread(target=run)
    thread.start()
    assert started.wait(1)
    sleep(0.38)
    # Without heartbeats, the original 0.3s lease would have expired here.
    assert queue.claim(agent, now=began + timedelta(seconds=0.4)) is None
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert errors == []
    assert results == ["completed_review_required"]
    assert queue.counts() == {"done": 1}
    queue.close()
    store.close()


def test_shared_runtime_atomically_persists_deliverable_and_completes_lease(tmp_path):
    agent, item, store, separate_queue = setup(tmp_path)
    separate_queue.close()
    queue = DurableWorkerQueue(store._connection, lock=store._lock)
    queue.enqueue(item.id, agent, {"source": "shared-runtime"})
    worker = OpenCompanyWorker(queue, store, FakeExecutor(), store)
    assert worker.run_once(agent, "marketplace_operations_analyst") == "completed_review_required"
    assert queue.counts() == {"done": 1}
    assert store.get_work_item(item.id).state == TaskState.REVIEW
    assert len(store.list_deliverables(item.id)) == 1
    assert store.audit_event_count() == 1
    assert store.verify_audit_chain()
    store.close()
