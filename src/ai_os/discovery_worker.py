"""Standalone worker for queued technology-discovery scans."""
import logging
import os
import time
from ai_os.db import initialize_database
from ai_os.discovery import run_pending_once

logging.basicConfig(level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ai_os.discovery_worker")

def main() -> None:
    initialize_database()
    poll = max(2, min(int(os.getenv("AI_OS_DISCOVERY_POLL_SECONDS", "5")), 60))
    logger.info("Technology discovery worker started; poll=%ss", poll)
    while True:
        try:
            if not run_pending_once():
                time.sleep(poll)
        except Exception:
            logger.exception("Discovery scan failed; worker will continue.")
            time.sleep(poll)

if __name__ == "__main__":
    main()
