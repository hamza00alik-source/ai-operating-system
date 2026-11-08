"""Minimal runtime scheduling hooks used by the supervised worker."""


def schedule_ready_steps() -> dict:
    """Reserved extension point for dependency-aware agent step scheduling.

    The starter task queue does not yet model multi-step agent graphs, so this
    function intentionally schedules no additional steps.
    """
    return {"scheduled": 0}
