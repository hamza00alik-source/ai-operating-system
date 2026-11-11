"""Deprecated standalone worker entry point.

OpenCompany deliberately runs workers inside the authenticated API process.
A second worker process cannot prove that the owner completed a live,
zero-cost provider test in that process, so it must never claim queued work.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("opencompany.worker")


def main() -> int:
    logger.error(
        "Standalone worker execution is disabled: start the API and use the "
        "owner dashboard to run the live free-provider test and start its "
        "in-process worker fleet."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
