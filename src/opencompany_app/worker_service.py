"""Dedicated single-instance worker for persistent OpenCompany deployments.

Run separately from the API against the same SQLite database and private env.
This worker is intentionally opt-in and processes only owner-admitted queue work.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from collections.abc import Callable
from uuid import UUID

from opencompany_app.runtime import create_runtime

logger = logging.getLogger("opencompany.worker")


def run_active_specialists_once(runtime) -> int:
    """Give each active specialist one queue claim; return completed task count."""
    completed = 0
    for agent in runtime.agents.values():
        if agent.get("state") != "active":
            continue
        try:
            agent_id = UUID(str(agent["id"]))
            role_key = str(agent["role_key"])
            result = runtime.worker.run_once(agent_id, role_key)
            if result != "idle":
                completed += 1
        except Exception:
            logger.exception("Specialist task failed safely for role %s", agent.get("role_key"))
    return completed


def run_worker_loop(*, runtime, poll_seconds: int = 5,
                    stop_requested: Callable[[], bool] = lambda: False,
                    sleep: Callable[[float], None] = time.sleep) -> None:
    interval = max(1, min(int(poll_seconds), 60))
    while not stop_requested():
        processed = run_active_specialists_once(runtime)
        if not processed and not stop_requested():
            sleep(interval)


def main() -> None:
    if os.getenv("OPENCOMPANY_WORKER_ENABLED", "").strip().lower() != "true":
        raise SystemExit("Worker disabled. Set OPENCOMPANY_WORKER_ENABLED=true to opt in.")
    database_path = os.getenv("OPENCOMPANY_DATABASE_PATH", "").strip()
    if not database_path or database_path == ":memory:":
        raise SystemExit("Set OPENCOMPANY_DATABASE_PATH to the same persistent SQLite file used by the API.")
    runtime = create_runtime(database_path)
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        runtime.close()
        raise SystemExit("No owner-confirmed zero-cost provider configured; worker did not start.")
    stop = {"requested": False}
    def request_stop(_signum, _frame):
        stop["requested"] = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        logger.info("OpenCompany worker started; single-instance mode; no paid fallback.")
        run_worker_loop(
            runtime=runtime,
            poll_seconds=int(os.getenv("OPENCOMPANY_WORKER_POLL_SECONDS", "5")),
            stop_requested=lambda: stop["requested"],
        )
    finally:
        runtime.close()
        logger.info("OpenCompany worker stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("OPENCOMPANY_LOG_LEVEL", "INFO").upper())
    main()
