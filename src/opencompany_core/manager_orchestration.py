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
from .workforce import RoleSpec, default_workforce, specialist_role_keys


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
    supporting_member: bool
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
    max_specialists: int = 15,
) -> ManagerDelegationPlan:
    """Choose manager handling or a bounded multi-team specialist plan for review."""
    if not 1 <= max_specialists <= 50:
        raise ValueError("max_specialists must be between 1 and 50")
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

    # Select across the highest-scoring coherent teams until the requested
    # bounded workforce size is reached. This lets a department manager use
    # multiple specialist teams rather than being permanently capped at one
    # five-person team.
    selected_roles: list[RoleSpec] = []
    selected_team_keys: list[str] = []
    for selected_team, _members in sorted(by_team.items(), key=team_score):
        team_roles = [
            workforce.get(role_key)
            for role_key in specialist_role_keys(item.department)
            if workforce.get(role_key).team_key == selected_team
        ]
        team_roles.sort(key=lambda role: (
            -sum(1 for capability in requested if capability in {
                value.casefold() for value in role.capabilities
            }),
            role.key,
        ))
        remaining = max_specialists - len(selected_roles)
        if remaining <= 0:
            break
        chosen = team_roles[:remaining]
        if chosen:
            selected_team_keys.append(selected_team)
            selected_roles.extend(chosen)

    selected = tuple(
        SpecialistSelection(
            role_key=role.key, title=role.title, team_key=role.team_key,
            matched_capabilities=tuple(
                capability for capability in requested
                if capability in {value.casefold() for value in role.capabilities}
            ),
            supporting_member=not any(
                capability in {value.casefold() for value in role.capabilities}
                for capability in requested
            ),
            permitted_outputs=role.permitted_outputs,
        )
        for role in selected_roles
    )
    covered = set(manager_covered) | {
        capability for member in selected for capability in member.matched_capabilities
    }
    uncovered = tuple(value for value in requested if value not in covered)
    mode = DelegationMode.SPECIALIST_TEAM if selected and not uncovered else DelegationMode.OWNER_REVIEW
    return ManagerDelegationPlan(
        work_item_id=str(item.id), department=item.department,
        manager_role_key=manager.key, manager_title=manager.title,
        mode=mode, selected_team_key=selected_team_keys[0] if len(selected_team_keys) == 1 else None,
        specialists=selected, manager_covered_capabilities=manager_covered,
        uncovered_capabilities=uncovered,
    )
