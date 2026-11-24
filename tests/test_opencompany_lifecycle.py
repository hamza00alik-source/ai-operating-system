import pytest
from uuid import uuid4

from opencompany_core.domain import TaskState, WorkItem
from opencompany_core.lifecycle import StateTransitionError, transition_work_item


def work(state, depends_on=()):
    return WorkItem(uuid4(), "Prepare deliverable", "Create a reviewed deliverable",
                    "operations", state=state, depends_on=depends_on)


def test_valid_work_lifecycle_requires_review_before_completion():
    item = work(TaskState.DRAFT)
    item = transition_work_item(item, TaskState.READY, known_items={})
    item = transition_work_item(item, TaskState.QUEUED, known_items={})
    item = transition_work_item(item, TaskState.IN_PROGRESS, known_items={})
    item = transition_work_item(item, TaskState.REVIEW, known_items={})
    item = transition_work_item(item, TaskState.COMPLETED, known_items={})
    assert item.state == TaskState.COMPLETED


def test_cannot_skip_quality_review():
    item = work(TaskState.IN_PROGRESS)
    with pytest.raises(StateTransitionError, match="not permitted"):
        transition_work_item(item, TaskState.COMPLETED, known_items={})


def test_cannot_queue_work_with_incomplete_dependency():
    prerequisite = work(TaskState.IN_PROGRESS)
    dependent = work(TaskState.READY, depends_on=(prerequisite.id,))
    with pytest.raises(StateTransitionError, match="dependencies are completed"):
        transition_work_item(dependent, TaskState.QUEUED,
                             known_items={prerequisite.id: prerequisite})


def test_can_queue_when_all_dependencies_are_completed():
    prerequisite = work(TaskState.COMPLETED)
    dependent = work(TaskState.READY, depends_on=(prerequisite.id,))
    queued = transition_work_item(dependent, TaskState.QUEUED,
                                  known_items={prerequisite.id: prerequisite})
    assert queued.state == TaskState.QUEUED


def test_completed_work_is_terminal():
    item = work(TaskState.COMPLETED)
    with pytest.raises(StateTransitionError, match="not permitted"):
        transition_work_item(item, TaskState.READY, known_items={})


def test_failed_work_can_be_retried_after_dependencies_complete():
    item = work(TaskState.FAILED)
    retried = transition_work_item(item, TaskState.READY, known_items={})
    assert retried.state == TaskState.READY
