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
