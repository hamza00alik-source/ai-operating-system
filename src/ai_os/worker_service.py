"""Combined background worker for discovery scans and AI agent runs."""
import logging
import os
import time
from uuid import uuid4

from ai_os.db import initialize_database
from ai_os.discovery import run_pending_once as run_discovery_once
from ai_os.agent_runtime import run_pending_once as run_agent_once

logger = logging.getLogger("ai_os.worker_service")


def main() -> None:
    logging.basicConfig(level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper())
    initialize_database()
    try:
        poll = int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "5"))
    except ValueError:
        poll = 5
    poll = max(2, min(poll, 60))
    worker_id = f"aios-worker-{uuid4()}"
    logger.info("AIOS background worker started; id=%s poll=%ss", worker_id, poll)

    while True:
        did_work = False
        try:
            did_work = run_discovery_once(worker_id=f"{worker_id}-discovery") or did_work
            did_work = run_agent_once(worker_id=f"{worker_id}-agent") or did_work
        except Exception:
            logger.exception("Background worker cycle failed.")
            time.sleep(poll)
        if not did_work:
            time.sleep(poll)


if __name__ == "__main__":
    main()
