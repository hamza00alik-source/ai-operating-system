"""Compatibility entry point for the implemented discovery worker.

The general-purpose agent runtime is not yet part of this repository. This module
intentionally delegates only to the working discovery worker rather than
importing nonexistent agent_runtime/model_adapter/worker modules.
"""
from ai_os.discovery_worker import main


if __name__ == "__main__":
    main()
