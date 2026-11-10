"""Supervised single-consumer worker entry point.

The production worker documented in docs/WORKER.md uses ai_os.worker. This
module remains a supported serial alternative with process-level backoff.
Workflow DAG readiness is released transactionally by finish_workflow_task;
there is no separate schedule_ready_steps stage.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from uuid import uuid4

from ai_os.agent_runtime import recover_interrupted_runs, run_pending_once
from ai_os.db import initialize_database
from ai_os.llm_gateway import list_providers

logger = logging.getLogger("ai_os.worker_service")


def _run_once(*, worker_id: str) -> dict:
    """Adapt the queue's boolean result to the supervisor's result contract."""
    return {"processed": bool(run_pending_once()), "worker_id": worker_id}


def run_worker_loop(
    *,
    worker_id: str,
    poll_seconds: int,
    stop_requested: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
    schedule: Callable[[], dict] | None = None,
    run: Callable[..., dict] = _run_once,
    on_error: Callable[[Exception, int], None] | None = None,
) -> None:
    """Run until stopped; exponentially back off after process-level failures."""
    delay = max(1, min(int(poll_seconds), 60))
    failure_count = 0
    while not stop_requested():
        try:
            scheduled = schedule() if schedule is not None else {"scheduled": 0}
            result = run(worker_id=worker_id)
            failure_count = 0
            if result.get("processed") or scheduled.get("scheduled"):
                continue
            sleep(delay)
        except Exception as exc:
            failure_count += 1
            backoff = min(60, delay * (2 ** min(failure_count - 1, 6)))
            if on_error is not None:
                on_error(exc, backoff)
            else:
                logger.exception(
                    "Worker loop recovered from process-level failure; retry in %ss",
                    backoff,
                )
            if not stop_requested():
                sleep(backoff)


def main() -> None:
    initialize_database()
    providers = [item for item in list_providers() if item.get("eligible")]
    if not providers:
        raise SystemExit(
            "Agent worker not started: configure and owner-confirm at least one free model provider. "
            "No model request was made."
        )
    status = providers[0]

    try:
        interval = int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "3"))
    except ValueError:
        interval = 3
    interval = max(1, min(interval, 60))
    recovered = recover_interrupted_runs()
    worker_id = f"agent-worker-{uuid4()}"
    logger.info(
        "Agent worker started: %s; provider=%s; model=%s; recovered=%s",
        worker_id, status["id"], status["model"], recovered,
    )

    stop_event = threading.Event()

    def request_stop(signum, _frame) -> None:
        logger.info("Received signal %s; stopping after the current task.", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run_worker_loop(
        worker_id=worker_id,
        poll_seconds=interval,
        stop_requested=stop_event.is_set,
    )
    logger.info("Agent worker stopped cleanly.")


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    main()
