"""Dedicated long-running AIOS agent worker process.

Run as a separate service alongside the API:
    python -m ai_os.worker

The API and worker must share the same persistent SQLite database volume.
Run exactly one worker replica until the queue is moved to a server database
with distributed locking and worker leases.
"""
from __future__ import annotations

import logging
import os
import signal
import threading

from ai_os.agent_runtime import recover_interrupted_runs, worker_loop
from ai_os.db import initialize_database


def main() -> None:
    logging.basicConfig(
        level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    poll_seconds = max(1, min(int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "3")), 30))
    initialize_database()
    recovered = recover_interrupted_runs()
    logging.getLogger("ai_os.worker").info(
        "Dedicated worker initialized; recovered %s interrupted run(s).", recovered
    )
    stop_event = threading.Event()

    def request_stop(signum, _frame) -> None:
        logging.getLogger("ai_os.worker").info("Received signal %s; stopping after current task.", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker_loop(stop_event, poll_seconds=poll_seconds)


if __name__ == "__main__":
    main()
