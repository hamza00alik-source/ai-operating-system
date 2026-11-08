"""Supervised durable agent worker process.

The queue owns per-job retries and stale-lease recovery. This module adds a
process-level supervisor so transient scheduler/database errors do not terminate
the worker. A service manager should still restart the process after host failure.
"""
import logging
import os
import time
from uuid import uuid4
from collections.abc import Callable

from ai_os.agent_runtime import schedule_ready_steps
from ai_os.model_adapter import get_model_status
from ai_os.worker import run_once

logger = logging.getLogger("ai_os.worker_service")


def run_worker_loop(
    *,
    worker_id: str,
    poll_seconds: int,
    stop_requested: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
    schedule: Callable[[], dict] = schedule_ready_steps,
    run: Callable[..., dict] = run_once,
    on_error: Callable[[Exception, int], None] | None = None,
) -> None:
    """Run until stopped; exponentially back off after process-level failures."""
    delay = max(1, min(int(poll_seconds), 60))
    failure_count = 0
    while not stop_requested():
        try:
            scheduled = schedule()
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
    status = get_model_status()
    if not status["enabled"] or not status["configured"]:
        raise SystemExit(
            "Agent worker not started: configure AI_OS_MODEL_BASE_URL and "
            "AI_OS_MODEL_NAME, then explicitly set AI_OS_MODEL_ENABLED=true. "
            "No model request was made."
        )
    try:
        interval = int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "3"))
    except ValueError:
        interval = 3
    interval = max(1, min(interval, 60))
    worker_id = f"agent-worker-{uuid4()}"
    logger.info(
        "Agent worker started: %s; provider=%s; model=%s",
        worker_id, status["provider"], status["model"],
    )
    run_worker_loop(
        worker_id=worker_id,
        poll_seconds=interval,
        stop_requested=lambda: False,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Agent worker stopped cleanly.")
