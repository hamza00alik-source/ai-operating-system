"""ASGI-host-compatible launcher for the separate OpenCompany worker."""
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from opencompany_app.worker_service import main  # noqa: E402


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("OPENCOMPANY_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    main()
