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
from opencompany_core.persistence import SQLiteStore
from opencompany_core.worker_queue import DurableWorkerQueue
from opencompany_core.worker_runner import OpenCompanyWorker


@dataclass(slots=True)
class OpenCompanyRuntime:
    store: SQLiteStore
    queue: DurableWorkerQueue
    worker: OpenCompanyWorker

    def close(self) -> None:
        # Queue shares the store connection; only the store owns its lifecycle.
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
    queue = DurableWorkerQueue(
        store._connection,
        max_attempts=int(os.environ.get("OPENCOMPANY_WORKER_MAX_ATTEMPTS", "3")),
        lease_seconds=int(os.environ.get("OPENCOMPANY_WORKER_LEASE_SECONDS", "300")),
        lock=store._lock,
    )
    executor = AgentExecutor()
    worker = OpenCompanyWorker(
        queue=queue,
        store=store,
        executor=executor,
        artifact_sink=store,
        request_budget_usd=0.0,
        preferred_provider="unorouter",
    )
    return OpenCompanyRuntime(store=store, queue=queue, worker=worker)
