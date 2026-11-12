"""Independent planning rules for OpenCompany work.

The planner is deterministic and side-effect free. It never executes work or
contacts an external service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
from uuid import UUID

from .domain import ApprovalDecision, ApprovalState, TaskState, WorkItem


class PlanError(ValueError):
    """Raised when a proposed work plan is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class WorkPlan:
    items: tuple[WorkItem, ...]

    def __post_init__(self) -> None:
        by_id = {item.id: item for item in self.items}
        if len(by_id) != len(self.items):
            raise PlanError("work item identifiers must be unique")
        for item in self.items:
            missing = set(item.depends_on) - by_id.keys()
            if missing:
                raise PlanError(f"work item {item.id} references unknown dependencies")
            if any(by_id[dependency].business_id != item.business_id for dependency in item.depends_on):
                raise PlanError("work item dependencies cannot cross business-unit boundaries")
        _assert_acyclic(by_id)

    @property
    def by_id(self) -> Mapping[UUID, WorkItem]:
        return {item.id: item for item in self.items}

    def ready_items(self) -> tuple[WorkItem, ...]:
        """Return READY items whose complete dependency set has succeeded."""
        by_id = self.by_id
        eligible = [
            item for item in self.items
            if item.state == TaskState.READY
            and all(by_id[dependency].state == TaskState.COMPLETED
                    for dependency in item.depends_on)
        ]
        return tuple(sorted(eligible, key=lambda item: (item.created_at, str(item.id))))

    def blocked_items(self) -> tuple[WorkItem, ...]:
        """Return READY items that are waiting on one or more dependencies."""
        by_id = self.by_id
        waiting = [
            item for item in self.items
            if item.state == TaskState.READY
            and any(by_id[dependency].state != TaskState.COMPLETED
                    for dependency in item.depends_on)
        ]
        return tuple(sorted(waiting, key=lambda item: (item.created_at, str(item.id))))

    def dependency_chain(self, item_id: UUID) -> tuple[UUID, ...]:
        """Return all transitive prerequisites in stable dependency-first order."""
        by_id = self.by_id
        if item_id not in by_id:
            raise PlanError("requested work item does not exist")
        ordered: list[UUID] = []
        visited: set[UUID] = set()

        def visit(current: UUID) -> None:
            for dependency in sorted(by_id[current].depends_on, key=str):
                if dependency not in visited:
                    visit(dependency)
                    visited.add(dependency)
                    ordered.append(dependency)

        visit(item_id)
        return tuple(ordered)


def _assert_acyclic(by_id: Mapping[UUID, WorkItem]) -> None:
    visiting: set[UUID] = set()
    visited: set[UUID] = set()

    def visit(item_id: UUID) -> None:
        if item_id in visiting:
            raise PlanError("dependency cycle detected")
        if item_id in visited:
            return
        visiting.add(item_id)
        for dependency in by_id[item_id].depends_on:
            visit(dependency)
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in by_id:
        visit(item_id)


_PROTECTED_ACTIONS = frozenset({
    "publish", "purchase", "pay", "send_customer_message",
    "make_customer_commitment", "change_production", "change_credentials",
    "deploy_production", "delete_customer_data",
})


def action_requires_owner_approval(action: str) -> bool:
    """Classify high-impact operations that must never be self-approved."""
    return action.strip().lower() in _PROTECTED_ACTIONS


def authorize_action(
    *,
    action: str,
    target_type: str,
    target_id: str,
    approval: ApprovalDecision | None,
) -> bool:
    """Check a specific approval; this function never performs the action."""
    if not action.strip() or not target_type.strip() or not target_id.strip():
        raise ValueError("action and target identity are required")
    if not action_requires_owner_approval(action):
        return True
    if approval is None:
        return False
    return (
        approval.state == ApprovalState.APPROVED
        and approval.action == action
        and approval.target_type == target_type
        and approval.target_id == target_id
        and approval.decided_by is not None
        and approval.decided_by.strip().lower() == "owner"
    )
