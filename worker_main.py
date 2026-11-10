"""Foreground worker fleet entry point for OpenCompany.

Run under a process manager. It never starts from API import, and it only
claims owner-admitted work assigned to explicitly ACTIVE agent profiles.
"""
from __future__ import annotations

import logging
import os
import time

from opencompany_app.runtime import create_runtime


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("opencompany.worker")


def main() -> None:
    runtime = create_runtime()
    idle_sleep = max(0.1, min(60.0, float(os.environ.get("OPENCOMPANY_WORKER_IDLE_SECONDS", "2"))))
    logger.info("OpenCompany worker fleet started; no agent is activated by this process.")
    try:
        while True:
            active = [
                agent for agent in runtime.store.list_agents(limit=1000)
                if agent.state.value == "active" and agent.role_key
            ]
            did_work = False
            for agent in active:
                try:
                    result = runtime.worker.run_once(agent.id, agent.role_key)
                    did_work = did_work or result != "idle"
                except Exception as exc:
                    logger.warning(
                        "Worker cycle failed for agent=%s role=%s error_type=%s",
                        agent.id, agent.role_key, type(exc).__name__,
                    )
            if not did_work:
                time.sleep(idle_sleep)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
