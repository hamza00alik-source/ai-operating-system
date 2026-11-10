"""Dependency graph helpers for parallel department workflows."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

# One-based sequence numbers for the company operating cycle.
COMPANY_CYCLE_DEPENDENCIES: dict[int, tuple[int, ...]] = {
    1: (),
    2: (1,),
    3: (2,),
    4: (3,),
    5: (3,),
    6: (2, 3),
    7: (4, 5, 6),
    8: (7,),
    9: (7,),
    10: (7,),
    11: (3, 7),
    12: (8, 9, 10, 11),
}


def validate_dependencies(graph: dict[int, Iterable[int]]) -> None:
    """Reject missing nodes, self-dependencies and cycles before a run is created."""
    nodes = set(graph)
    normalized = {node: set(deps) for node, deps in graph.items()}
    for node, deps in normalized.items():
        if node in deps:
            raise ValueError(f"Step {node} cannot depend on itself")
        missing = deps - nodes
        if missing:
            raise ValueError(f"Step {node} references missing dependencies: {sorted(missing)}")
    indegree = {node: len(deps) for node, deps in normalized.items()}
    children: dict[int, list[int]] = defaultdict(list)
    for node, deps in normalized.items():
        for dependency in deps:
            children[dependency].append(node)
    ready = deque(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited != len(nodes):
        raise ValueError("Workflow dependency graph contains a cycle")


def ready_steps(graph: dict[int, Iterable[int]], completed: Iterable[int],
                pending: Iterable[int] | None = None) -> list[int]:
    """Return pending steps whose full prerequisite set has completed."""
    validate_dependencies(graph)
    completed_set = set(completed)
    pending_set = set(pending) if pending is not None else set(graph) - completed_set
    return sorted(node for node in pending_set
                  if node in graph and set(graph[node]).issubset(completed_set))


def parallel_layers(graph: dict[int, Iterable[int]]) -> list[list[int]]:
    """Return deterministic execution waves; nodes in a wave can run concurrently."""
    validate_dependencies(graph)
    remaining = {node: set(deps) for node, deps in graph.items()}
    layers: list[list[int]] = []
    completed: set[int] = set()
    while remaining:
        layer = sorted(node for node, deps in remaining.items() if deps.issubset(completed))
        if not layer:
            raise ValueError("Workflow dependency graph cannot make progress")
        layers.append(layer)
        completed.update(layer)
        for node in layer:
            remaining.pop(node)
    return layers
