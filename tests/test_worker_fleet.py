from types import SimpleNamespace
from uuid import uuid4

from opencompany_core.worker_fleet import WorkerFleet


class QueueAwareWorker:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.fleet = None
        self.calls = []

    def available_agent_ids(self):
        return (self.agent_id,)

    def run_once(self, agent_id, role_key):
        self.calls.append((agent_id, role_key))
        self.fleet._stop.set()
        return "completed_review_required"


class DirectAgentStore:
    def __init__(self, agent):
        self.agent = agent
        self.lookups = []

    def get_agent(self, agent_id):
        self.lookups.append(agent_id)
        return self.agent

    def list_agents(self, **kwargs):
        raise AssertionError("worker fleet must not scan the entire workforce")


def test_worker_fleet_looks_up_only_agents_with_claimable_work():
    agent_id = uuid4()
    agent = SimpleNamespace(id=agent_id, state=SimpleNamespace(value="active"), role_key="research_specialist")
    worker = QueueAwareWorker(agent_id)
    store = DirectAgentStore(agent)
    fleet = WorkerFleet(worker, store, idle_poll_seconds=0.1)
    worker.fleet = fleet

    fleet._run()

    assert store.lookups == [agent_id]
    assert worker.calls == [(agent_id, "research_specialist")]
    status = fleet.status()
    assert status.completed_cycles == 1
    assert status.failed_cycles == 0


def test_worker_fleet_runs_independent_specialists_concurrently():
    import threading

    agent_ids = (uuid4(), uuid4())
    class ConcurrentWorker:
        def __init__(self):
            self.fleet = None
            self.lock = threading.Lock()
            self.active = set()
            self.max_active = 0
            self.both_started = threading.Event()
            self.release = threading.Event()
        def available_agent_ids(self):
            with self.lock:
                return tuple(value for value in agent_ids if value not in self.active)
        def run_once(self, agent_id, role_key):
            with self.lock:
                if agent_id in self.active:
                    return "idle"
                self.active.add(agent_id)
                self.max_active = max(self.max_active, len(self.active))
                if len(self.active) == 2:
                    self.both_started.set()
            self.release.wait(timeout=3)
            with self.lock:
                self.active.discard(agent_id)
            self.fleet._stop.set()
            return "completed_review_required"

    class AgentStore:
        def get_agent(self, agent_id):
            return SimpleNamespace(
                id=agent_id, state=SimpleNamespace(value="active"),
                role_key=f"specialist_{str(agent_id)[:6]}",
            )

    worker = ConcurrentWorker()
    fleet = WorkerFleet(worker, AgentStore(), idle_poll_seconds=0.1, concurrency=2)
    worker.fleet = fleet
    assert fleet.start() is True
    assert worker.both_started.wait(timeout=3)
    assert worker.max_active == 2
    worker.release.set()
    assert fleet.stop(timeout_seconds=3) is True
    status = fleet.status()
    assert status.running is False
    assert status.concurrency == 2
    assert status.completed_cycles == 2


def test_worker_fleet_concurrency_is_bounded():
    import pytest
    import threading

    worker = QueueAwareWorker(uuid4())
    store = DirectAgentStore(SimpleNamespace(
        id=worker.agent_id, state=SimpleNamespace(value="active"), role_key="research_specialist",
    ))
    with pytest.raises(ValueError):
        WorkerFleet(worker, store, concurrency=0)
    with pytest.raises(ValueError):
        WorkerFleet(worker, store, concurrency=17)
