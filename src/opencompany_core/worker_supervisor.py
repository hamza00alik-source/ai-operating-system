"""Graceful, bounded foreground supervisor for an OpenCompany worker.

Run this from a process manager (for example, a container supervisor). The
class does not daemonize, install signal handlers, or start itself on import.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Event
from uuid import UUID

from .worker_runner import OpenCompanyWorker


logger = logging.getLogger(__name__)


class WorkerSupervisorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SupervisorSummary:
    completed: int
    idle_cycles: int
    failed_cycles: int
    stopped: bool


class WorkerSupervisor:
    """Poll one worker with graceful stop and a consecutive-failure circuit breaker."""

    def __init__(
        self,
        worker: OpenCompanyWorker,
        agent_id: UUID,
        role_key: str,
        *,
        idle_poll_seconds: float = 2.0,
        failure_backoff_seconds: float = 5.0,
        max_consecutive_failures: int = 5,
    ) -> None:
        if not 0.1 <= idle_poll_seconds <= 60:
            raise ValueError("idle_poll_seconds must be between 0.1 and 60")
        if not 0.1 <= failure_backoff_seconds <= 60:
            raise ValueError("failure_backoff_seconds must be between 0.1 and 60")
        if not 1 <= max_consecutive_failures <= 20:
            raise ValueError("max_consecutive_failures must be between 1 and 20")
        self.worker = worker
        self.agent_id = agent_id
        self.role_key = role_key
        self.idle_poll_seconds = idle_poll_seconds
        self.failure_backoff_seconds = failure_backoff_seconds
        self.max_consecutive_failures = max_consecutive_failures

    def run(self, stop_event: Event, *, cycle_limit: int | None = None) -> SupervisorSummary:
        """Run until stopped, or until the optional bounded cycle limit is reached."""
        if cycle_limit is not None and not 1 <= cycle_limit <= 100000:
            raise ValueError("cycle_limit must be between 1 and 100000")
        completed = idle = failed = consecutive_failures = cycles = 0

        while not stop_event.is_set():
            if cycle_limit is not None and cycles >= cycle_limit:
                break
            cycles += 1
            try:
                result = self.worker.run_once(self.agent_id, self.role_key)
                consecutive_failures = 0
                if result == "idle":
                    idle += 1
                    if stop_event.wait(self.idle_poll_seconds):
                        break
                else:
                    completed += 1
            except Exception as exc:
                failed += 1
                consecutive_failures += 1
                logger.warning(
                    "OpenCompany worker cycle failed; error_type=%s consecutive_failures=%d",
                    type(exc).__name__, consecutive_failures,
                )
                if consecutive_failures >= self.max_consecutive_failures:
                    raise WorkerSupervisorError(
                        "worker stopped after reaching the consecutive-failure limit"
                    ) from exc
                if stop_event.wait(self.failure_backoff_seconds):
                    break

        return SupervisorSummary(
            completed=completed, idle_cycles=idle, failed_cycles=failed,
            stopped=stop_event.is_set(),
        )
