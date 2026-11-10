"""Manager-led team selection for internal OpenCompany work.

This module creates reviewable delegation plans only. It does not persist
assignments, activate agents, enqueue work, invoke models, or perform actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .domain import WorkItem
from .organization import default_organization
from .workforce import RoleSpec, default_workforce


class DelegationMode(StrEnum):
    MANAGER_DIRECT = "manager_direct"
    SPECIALIST_TEAM = "specialist_team"
    OWNER_REVIEW = "owner_review"


@dataclass(frozen=True, slots=True)
class SpecialistSelection:
    role_key: str
    title: str
    team_key: str
    matched_capabilities: tuple[str, ...]
    permitted_outputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManagerDelegationPlan:
    work_item_id: str
    department: str
    manager_role_key: str
    manager_title: str
    mode: DelegationMode
    selected_team_key: str | None
    specialists: tuple[SpecialistSelection, ...]
    manager_covered_capabilities: tuple[str, ...]
    uncovered_capabilities: tuple[str, ...]
    assignment_performed: bool = False
    execution_started: bool = False


def plan_department_work(
    item: WorkItem,
    required_capabilities: Iterable[str],
    *,
    max_specialists: int = 5,
) -> ManagerDelegationPlan:
    """Choose direct manager handling or a single specialist team for review."""
    if not 1 <= max_specialists <= 5:
        raise ValueError("max_specialists must be between 1 and 5")
    requested = tuple(sorted({
        value.strip().casefold() for value in required_capabilities
        if isinstance(value, str) and value.strip()
    }))
    if not requested:
        raise ValueError("at least one required capability is necessary")

    organization = default_organization()
    department = organization.get(item.department)
    workforce = default_workforce()
    manager = workforce.get(department.manager_role_key)
    manager_capabilities = {value.casefold() for value in manager.capabilities}
    manager_covered = tuple(value for value in requested if value in manager_capabilities)

    if len(manager_covered) == len(requested):
        return ManagerDelegationPlan(
            work_item_id=str(item.id), department=item.department,
            manager_role_key=manager.key, manager_title=manager.title,
            mode=DelegationMode.MANAGER_DIRECT, selected_team_key=None,
            specialists=(), manager_covered_capabilities=manager_covered,
            uncovered_capabilities=(),
        )

    candidates = workforce.match_in_department(item.department, requested)
    if not candidates:
        return ManagerDelegationPlan(
            work_item_id=str(item.id), department=item.department,
            manager_role_key=manager.key, manager_title=manager.title,
            mode=DelegationMode.OWNER_REVIEW, selected_team_key=None,
            specialists=(), manager_covered_capabilities=manager_covered,
            uncovered_capabilities=tuple(value for value in requested if value not in manager_covered),
        )

    by_team: dict[str, list[tuple[int, RoleSpec, tuple[str, ...]]]] = {}
    for role in candidates:
        matched = tuple(value for value in requested if value in {
            capability.casefold() for capability in role.capabilities
        })
        by_team.setdefault(role.team_key, []).append((len(matched), role, matched))

    def team_score(entry: tuple[str, list[tuple[int, RoleSpec, tuple[str, ...]]]]):
        team_key, members = entry
        coverage = {capability for _, _, matched in members for capability in matched}
        total = sum(score for score, _, _ in members)
        return (-len(coverage), -total, team_key)

    selected_team, members = sorted(by_team.items(), key=team_score)[0]
    members.sort(key=lambda value: (-value[0], value[1].key))
    selected = tuple(
        SpecialistSelection(
            role_key=role.key, title=role.title, team_key=role.team_key,
            matched_capabilities=matched,
            permitted_outputs=role.permitted_outputs,
        )
        for _, role, matched in members[:max_specialists]
    )
    covered = set(manager_covered) | {
        capability for member in selected for capability in member.matched_capabilities
    }
    uncovered = tuple(value for value in requested if value not in covered)
    mode = DelegationMode.SPECIALIST_TEAM if selected and not uncovered else DelegationMode.OWNER_REVIEW
    return ManagerDelegationPlan(
        work_item_id=str(item.id), department=item.department,
        manager_role_key=manager.key, manager_title=manager.title,
        mode=mode, selected_team_key=selected_team if selected else None,
        specialists=selected, manager_covered_capabilities=manager_covered,
        uncovered_capabilities=uncovered,
    )
