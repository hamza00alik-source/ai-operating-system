"""Standalone, lease-aware worker for queued technology-discovery scans."""
import logging
import os
import time
from uuid import uuid4

from ai_os.db import initialize_database
from ai_os.discovery import run_pending_once

logger = logging.getLogger("ai_os.discovery_worker")


def main() -> None:
    logging.basicConfig(level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper())
    initialize_database()
    try:
        poll = int(os.getenv("AI_OS_DISCOVERY_POLL_SECONDS", "5"))
    except ValueError:
        poll = 5
    poll = max(2, min(poll, 60))
    worker_id = f"discovery-worker-{uuid4()}"
    logger.info("Technology discovery worker started; id=%s poll=%ss", worker_id, poll)
    while True:
        try:
            if not run_pending_once(worker_id=worker_id):
                time.sleep(poll)
        except Exception:
            logger.exception("Discovery scan failed; lease released for retry.")
            time.sleep(poll)


if __name__ == "__main__":
    main()
