"""Optional single-service worker runner for constrained hosting plans.

When enabled, the worker runs in a managed background thread inside the API
process. Use one ASGI process (the supplied main.py default) and persistent
shared storage. For larger deployments, prefer a separate worker process.
"""
from __future__ import annotations

import logging
import os
from threading import Event, Thread
from uuid import uuid4

from ai_os.model_adapter import get_model_status
from ai_os.worker_service import run_worker_loop

logger = logging.getLogger("ai_os.embedded_worker")


def start_embedded_worker():
    """Start the worker only when explicitly enabled and model config is valid.

    Returns an idempotent shutdown callback for the application lifespan.
    """
    enabled = os.getenv("AI_OS_WORKER_EMBEDDED", "false").strip().lower() in {
        "1", "true", "yes",
    }
    if not enabled:
        return None

    status = get_model_status()
    if not status["enabled"] or not status["configured"]:
        raise RuntimeError(
            "AI_OS_WORKER_EMBEDDED=true requires AI_OS_MODEL_ENABLED=true, "
            "AI_OS_MODEL_BASE_URL and AI_OS_MODEL_NAME."
        )

    try:
        interval = int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "3"))
    except ValueError:
        interval = 3
    interval = max(1, min(interval, 60))
    worker_id = f"embedded-agent-worker-{uuid4()}"
    stop_event = Event()

    def run():
        run_worker_loop(
            worker_id=worker_id,
            poll_seconds=interval,
            stop_requested=stop_event.is_set,
            sleep=stop_event.wait,
        )

    thread = Thread(target=run, name="aios-embedded-worker", daemon=True)
    thread.start()
    logger.info(
        "Embedded agent worker started: %s; provider=%s; model=%s",
        worker_id, status["provider"], status["model"],
    )

    def stop():
        stop_event.set()
        thread.join(timeout=55)
        if thread.is_alive():
            logger.error("Embedded worker did not stop within 55 seconds: %s", worker_id)

    return stop
