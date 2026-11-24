"""Composition layer connecting approved brain memory, skills and workers."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from opencompany.brain import Brain
from opencompany.skills import SkillRegistry
from opencompany.worker import Worker


def build_skill_worker(
    queue,
    worker_id: str,
    registry: SkillRegistry,
    routes: Mapping[str, tuple[str, str]],
    *,
    approval_resolver: Callable[[str, str, dict], bool] | None = None,
    brain: Brain | None = None,
    memory_scope: str = "company",
    lease_seconds: int = 60,
) -> Worker:
    """Build a worker with explicit, read-only approved-memory enrichment.

    A job may provide memory_query to request context. It cannot inject
    memory_context directly: the runtime overwrites that field with approved
    records retrieved from the Brain. Sensitive action approval is resolved
    separately by trusted server-side code.
    """
    if not routes:
        raise ValueError("At least one skill route is required")
    if not isinstance(memory_scope, str) or not memory_scope.strip():
        raise ValueError("memory_scope must be a non-empty string")
    handlers = {}
    for handler_name, route in routes.items():
        if not isinstance(handler_name, str) or not handler_name.strip():
            raise ValueError("Handler names must be non-empty strings")
        if not isinstance(route, tuple) or len(route) != 2:
            raise ValueError("Each route must be a (skill_key, action) tuple")
        skill_key, action = route
        if not skill_key or not action:
            raise ValueError("Skill key and action are required in every route")
        skill_handler = registry.worker_handler(
            skill_key, action, approval_resolver=approval_resolver
        )

        def dispatch(payload, handler=skill_handler):
            safe_payload = dict(payload)
            query = safe_payload.pop("memory_query", "")
            # Never trust a caller-supplied memory context.
            safe_payload.pop("memory_context", None)
            if brain is not None and query:
                safe_payload["memory_context"] = brain.recall(
                    query, scope=memory_scope
                )
            return handler(safe_payload)

        handlers[handler_name] = dispatch
    return Worker(queue, worker_id, handlers, lease_seconds=lease_seconds)
