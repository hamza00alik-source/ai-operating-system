"""Compatibility entry point for the disabled standalone worker command.

Workers run only inside the authenticated API process after an owner-triggered
zero-cost provider verification. A separate process cannot satisfy that gate.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("opencompany.worker")


def main() -> int:
    logger.error(
        "Standalone worker execution is disabled: start the API and use the "
        "owner dashboard to verify the free provider and start its in-process fleet."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
