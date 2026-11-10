"""Explicitly controlled in-process worker fleet for a persistent API host."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from uuid import UUID

from .persistence import SQLiteStore
from .worker_runner import OpenCompanyWorker


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerFleetStatus:
    running: bool
    completed_cycles: int
    idle_cycles: int
    failed_cycles: int


class WorkerFleet:
    """Run active assigned profiles only after an explicit owner start command."""

    def __init__(
        self,
        worker: OpenCompanyWorker,
        store: SQLiteStore,
        *,
        idle_poll_seconds: float = 2.0,
    ) -> None:
        if not 0.1 <= idle_poll_seconds <= 60:
            raise ValueError("idle_poll_seconds must be between 0.1 and 60")
        self.worker = worker
        self.store = store
        self.idle_poll_seconds = idle_poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._completed = 0
        self._idle = 0
        self._failed = 0

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="opencompany-worker-fleet", daemon=True
            )
            self._thread.start()
            return True

    def stop(self, *, timeout_seconds: float = 10.0) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop.set()
        thread.join(timeout=max(0.1, min(timeout_seconds, 30.0)))
        return not thread.is_alive()

    def status(self) -> WorkerFleetStatus:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return WorkerFleetStatus(running, self._completed, self._idle, self._failed)

    def _run(self) -> None:
        while not self._stop.is_set():
            available_ids = set(self.worker.available_agent_ids())
            if not available_ids:
                with self._lock:
                    self._idle += 1
                self._stop.wait(self.idle_poll_seconds)
                continue
            agents = (
                agent for agent in self.store.list_agents(limit=1000)
                if agent.id in available_ids and agent.state.value == "active" and agent.role_key
            )
            did_work = False
            for agent in agents:
                if self._stop.is_set():
                    break
                try:
                    result = self.worker.run_once(agent.id, agent.role_key)
                    with self._lock:
                        if result == "idle":
                            self._idle += 1
                        else:
                            self._completed += 1
                    did_work = did_work or result != "idle"
                except Exception as exc:
                    with self._lock:
                        self._failed += 1
                    logger.warning(
                        "OpenCompany worker cycle failed; agent=%s error_type=%s",
                        agent.id, type(exc).__name__,
                    )
            if not did_work:
                self._stop.wait(self.idle_poll_seconds)
