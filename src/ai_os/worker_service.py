"""Combined, supervised worker for AIOS discovery and agent queues.

Run as a separate process with: python -m ai_os.worker_service
This implementation uses the queue APIs that exist on the current main branch.
It deliberately does not enable embedded multi-process workers or paid inference.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from uuid import uuid4

from ai_os.agent_runtime import recover_interrupted_runs, run_pending_once as run_agent_once
from ai_os.db import initialize_database
from ai_os.discovery import run_pending_once as run_discovery_once

logger = logging.getLogger("ai_os.worker_service")


def _poll_seconds() -> int:
    try:
        value = int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "5"))
    except (TypeError, ValueError):
        value = 5
    return max(2, min(value, 60))


def run_worker_loop(*, worker_id: str, stop_event: threading.Event,
                    poll_seconds: int | None = None) -> None:
    """Process both queues serially; recover from transient cycle errors."""
    delay = max(2, min(int(poll_seconds or _poll_seconds()), 60))
    failures = 0
    while not stop_event.is_set():
        did_work = False
        try:
            # A discovery scan is processed before an agent run to keep research
            # ingestion responsive without creating another competing consumer.
            recovered = recover_interrupted_runs()
            if recovered:
                logger.warning("Recovered %s expired/interrupted agent run(s).", recovered)
            did_work = bool(run_discovery_once()) or did_work
            did_work = bool(run_agent_once(worker_id=worker_id)) or did_work
            failures = 0
        except Exception:
            failures += 1
            backoff = min(60, delay * (2 ** min(failures - 1, 4)))
            logger.exception("Worker cycle failed; retrying in %ss (worker=%s)", backoff, worker_id)
            stop_event.wait(backoff)
            continue
        if not did_work:
            stop_event.wait(delay)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    initialize_database()
    stop_event = threading.Event()

    def request_stop(signum, _frame):
        logger.info("Received signal %s; stopping after current queue operation.", signum)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)

    worker_id = f"aios-worker-{uuid4()}"
    logger.info("AIOS combined worker started: %s", worker_id)
    try:
        run_worker_loop(worker_id=worker_id, stop_event=stop_event)
    finally:
        logger.info("AIOS combined worker stopped: %s", worker_id)


if __name__ == "__main__":
    main()
