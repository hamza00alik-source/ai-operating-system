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

from ai_os.agent_runtime import recover_interrupted_runs, worker_pool
from ai_os.db import initialize_database
from ai_os.inbox_supervisor import inbox_supervisor_loop
from ai_os.executive_supervisor import executive_supervisor_loop


def main() -> None:
    logging.basicConfig(
        level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    poll_seconds = max(1, min(int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "3")), 30))
    concurrency = max(1, min(int(os.getenv("AI_OS_WORKER_CONCURRENCY", "2")), 4))
    initialize_database()
    recovered = recover_interrupted_runs()
    logging.getLogger("ai_os.worker").info(
        "Dedicated worker initialized with %s queue consumer(s); recovered %s interrupted run(s).", concurrency, recovered
    )
    stop_event = threading.Event()

    def request_stop(signum, _frame) -> None:
        logging.getLogger("ai_os.worker").info("Received signal %s; stopping after current task.", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    inbox_thread = threading.Thread(
        target=inbox_supervisor_loop,
        args=(stop_event, poll_seconds),
        name="aios-inbox-supervisor",
        daemon=True,
    )
    inbox_thread.start()
    executive_thread = threading.Thread(
        target=executive_supervisor_loop,
        args=(stop_event, max(15, poll_seconds)),
        name="aios-executive-supervisor",
        daemon=True,
    )
    executive_thread.start()
    try:
        worker_pool(stop_event, poll_seconds=poll_seconds, concurrency=concurrency)
    finally:
        stop_event.set()
        inbox_thread.join(timeout=10)
        executive_thread.join(timeout=10)


if __name__ == "__main__":
    main()
