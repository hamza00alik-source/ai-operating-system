"""Composition root for the independent OpenCompany runtime.

The API and worker process share one SQLite database. Queue admission, queue
claim, task-state transitions, and audit events therefore use one transaction
boundary. Importing this module never starts a worker.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from opencompany_core.execution import AgentExecutor
from opencompany_core.model_gateway import ModelGateway
from opencompany_core.unorouter_adapter import configured_unorouter_gateway
from opencompany_core.persistence import SQLiteStore
from opencompany_core.worker_queue import DurableWorkerQueue
from opencompany_core.worker_runner import OpenCompanyWorker
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.owner_sessions import OwnerSessionStore
from opencompany_core.worker_fleet import WorkerFleet
from opencompany_core.collaboration_store import HandoffRepository
from opencompany_core.learning_store import LearningRepository
from opencompany_core.github_evolution import GitHubEvolutionClient
from opencompany_core.api_anything import ApiAnythingClient
from opencompany_core.research_broker import ResearchBroker


@dataclass(slots=True)
class OpenCompanyRuntime:
    store: SQLiteStore
    queue: DurableWorkerQueue
    worker: OpenCompanyWorker
    delegations: DelegationRepository
    sessions: OwnerSessionStore
    fleet: WorkerFleet
    gateway: ModelGateway
    handoffs: HandoffRepository
    learning: LearningRepository
    github_evolution: GitHubEvolutionClient | None
    api_anything: ApiAnythingClient | None

    def close(self) -> None:
        # Queue shares the store connection; only the store owns its lifecycle.
        self.fleet.stop(timeout_seconds=5.0)
        self.delegations.close()
        self.store.close()


def create_runtime(database_path: str | None = None) -> OpenCompanyRuntime:
    """Build the complete API/worker composition without starting execution."""
    configured = database_path or os.environ.get(
        "OPENCOMPANY_DATABASE_PATH", "data/opencompany_core.sqlite3"
    )
    path = Path(configured).expanduser()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(path)
    delegations = DelegationRepository(path)
    sessions = OwnerSessionStore(store._connection, store._lock)
    handoffs = HandoffRepository(store._connection, store._lock)
    learning = LearningRepository(store._connection, store._lock)
    github_evolution = GitHubEvolutionClient.from_env()
    queue = DurableWorkerQueue(
        store._connection,
        max_attempts=int(os.environ.get("OPENCOMPANY_WORKER_MAX_ATTEMPTS", "3")),
        lease_seconds=int(os.environ.get("OPENCOMPANY_WORKER_LEASE_SECONDS", "300")),
        lock=store._lock,
    )
    gateway = configured_unorouter_gateway()
    api_anything = ApiAnythingClient.from_env()
    research_broker = ResearchBroker(api_anything, gateway) if api_anything is not None else None
    executor = AgentExecutor(
        gateway=gateway,
        learning_context=learning.list_learning_notes,
        research_broker=research_broker,
    )
    worker = OpenCompanyWorker(
        queue=queue,
        store=store,
        executor=executor,
        artifact_sink=store,
        request_budget_usd=0.0,
        preferred_provider="unorouter",
    )
    fleet = WorkerFleet(worker, store)
    return OpenCompanyRuntime(store=store, queue=queue, worker=worker, delegations=delegations, sessions=sessions, fleet=fleet, gateway=gateway, handoffs=handoffs, learning=learning, github_evolution=github_evolution, api_anything=api_anything)
