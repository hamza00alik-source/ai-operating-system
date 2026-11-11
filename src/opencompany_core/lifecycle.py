"""Explicit work-item lifecycle rules for OpenCompany."""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping
from uuid import UUID

from .domain import TaskState, WorkItem


class StateTransitionError(ValueError):
    """Raised when a work item cannot move to the requested state."""


_ALLOWED: Mapping[TaskState, frozenset[TaskState]] = {
    TaskState.DRAFT: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.READY: frozenset({TaskState.QUEUED, TaskState.BLOCKED, TaskState.CANCELLED}),
    TaskState.BLOCKED: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.QUEUED: frozenset({TaskState.IN_PROGRESS, TaskState.CANCELLED}),
    TaskState.IN_PROGRESS: frozenset({
        TaskState.REVIEW, TaskState.FAILED, TaskState.CANCELLED,
    }),
    TaskState.REVIEW: frozenset({
        TaskState.COMPLETED, TaskState.READY, TaskState.FAILED, TaskState.CANCELLED,
    }),
    TaskState.FAILED: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.COMPLETED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


def transition_work_item(
    item: WorkItem,
    target: TaskState,
    *,
    known_items: Mapping[UUID, WorkItem],
) -> WorkItem:
    """Return a new state value after validating the requested transition."""
    if target not in _ALLOWED[item.state]:
        raise StateTransitionError(
            f"transition from {item.state.value} to {target.value} is not permitted"
        )
    if target == TaskState.QUEUED:
        unresolved = [
            dependency for dependency in item.depends_on
            if dependency not in known_items
            or known_items[dependency].state != TaskState.COMPLETED
        ]
        if unresolved:
            raise StateTransitionError("work cannot be queued until all dependencies are completed")
    if target == TaskState.READY and item.state in {TaskState.BLOCKED, TaskState.FAILED, TaskState.REVIEW}:
        unresolved = [
            dependency for dependency in item.depends_on
            if dependency not in known_items
            or known_items[dependency].state != TaskState.COMPLETED
        ]
        if unresolved:
            raise StateTransitionError("work cannot be made ready while dependencies remain incomplete")
    return replace(item, state=target)
