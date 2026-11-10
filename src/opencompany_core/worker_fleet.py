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
    concurrency: int
    completed_cycles: int
    idle_cycles: int
    failed_cycles: int


class WorkerFleet:
    """Run owner-admitted tasks after explicit start or owner-configured autostart."""

    def __init__(
        self,
        worker: OpenCompanyWorker,
        store: SQLiteStore,
        *,
        idle_poll_seconds: float = 2.0,
        concurrency: int = 2,
    ) -> None:
        if not 0.1 <= idle_poll_seconds <= 60:
            raise ValueError("idle_poll_seconds must be between 0.1 and 60")
        if not 1 <= concurrency <= 16:
            raise ValueError("worker concurrency must be between 1 and 16")
        self.worker = worker
        self.store = store
        self.idle_poll_seconds = idle_poll_seconds
        self.concurrency = concurrency
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.RLock()
        self._completed = 0
        self._idle = 0
        self._failed = 0

    def start(self) -> bool:
        with self._lock:
            if any(thread.is_alive() for thread in self._threads):
                return False
            self._stop.clear()
            self._threads = [
                threading.Thread(
                    target=self._run,
                    name=f"opencompany-worker-{index + 1}",
                    daemon=True,
                )
                for index in range(self.concurrency)
            ]
            for thread in self._threads:
                thread.start()
            return True

    def stop(self, *, timeout_seconds: float = 10.0) -> bool:
        with self._lock:
            threads = tuple(self._threads)
            alive = tuple(thread for thread in threads if thread.is_alive())
            if not alive:
                return False
            self._stop.set()
        deadline = time.monotonic() + max(0.1, min(timeout_seconds, 30.0))
        for thread in alive:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in alive)

    def status(self) -> WorkerFleetStatus:
        with self._lock:
            running = any(thread.is_alive() for thread in self._threads)
            return WorkerFleetStatus(running, self.concurrency, self._completed, self._idle, self._failed)

    def _run(self) -> None:
        while not self._stop.is_set():
            available_ids = set(self.worker.available_agent_ids())
            if not available_ids:
                with self._lock:
                    self._idle += 1
                self._stop.wait(self.idle_poll_seconds)
                continue
            did_work = False
            for agent_id in sorted(available_ids, key=str):
                if self._stop.is_set():
                    break
                agent = self.store.get_agent(agent_id)
                if agent is None or agent.state.value != "active" or not agent.role_key:
                    continue
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
