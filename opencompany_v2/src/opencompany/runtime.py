"""Composition layer connecting registered skills to the durable worker."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from opencompany.skills import SkillRegistry
from opencompany.worker import Worker


def build_skill_worker(
    queue,
    worker_id: str,
    registry: SkillRegistry,
    routes: Mapping[str, tuple[str, str]],
    *,
    approval_resolver: Callable[[str, str, dict], bool] | None = None,
    lease_seconds: int = 60,
) -> Worker:
    """Build a worker whose named handlers dispatch only registered skills.

    routes maps queue handler names to (skill_key, action). Approval resolution
    is injected by trusted application code; it is never read from job claims.
    """
    if not routes:
        raise ValueError("At least one skill route is required")
    handlers = {}
    for handler_name, route in routes.items():
        if not isinstance(handler_name, str) or not handler_name.strip():
            raise ValueError("Handler names must be non-empty strings")
        if not isinstance(route, tuple) or len(route) != 2:
            raise ValueError("Each route must be a (skill_key, action) tuple")
        skill_key, action = route
        if not skill_key or not action:
            raise ValueError("Skill key and action are required in every route")
        handlers[handler_name] = registry.worker_handler(
            skill_key, action, approval_resolver=approval_resolver
        )
    return Worker(queue, worker_id, handlers, lease_seconds=lease_seconds)
