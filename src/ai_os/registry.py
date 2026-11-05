"""Load and validate the local, provider-neutral agent catalog."""
from __future__ import annotations
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parents[2] / "agents" / "catalog.json"

@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    department: str
    description: str
    capabilities: tuple[str, ...]
    requires_approval_for: tuple[str, ...]
    enabled: bool

@lru_cache(maxsize=1)
def load_agents() -> tuple[AgentDefinition, ...]:
    """Read the checked-in catalog; fail closed on malformed or duplicate IDs."""
    payload: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported agent catalog schema_version")
    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list):
        raise ValueError("Agent catalog must contain an agents list")
    agents: list[AgentDefinition] = []
    seen: set[str] = set()
    for raw in raw_agents:
        agent_id = raw.get("id")
        if not isinstance(agent_id, str) or not agent_id.strip() or agent_id in seen:
            raise ValueError("Agent IDs must be non-empty and unique")
        seen.add(agent_id)
        agents.append(AgentDefinition(
            id=agent_id, name=str(raw["name"]), department=str(raw["department"]),
            description=str(raw["description"]),
            capabilities=tuple(raw.get("capabilities", [])),
            requires_approval_for=tuple(raw.get("requires_approval_for", [])),
            enabled=bool(raw.get("enabled", False)),
        ))
    return tuple(agents)

def list_agents(*, enabled_only: bool = True) -> list[AgentDefinition]:
    return [agent for agent in load_agents() if agent.enabled or not enabled_only]

def select_agent(department: str) -> AgentDefinition | None:
    """Exact department routing only; no unsafe fuzzy matching."""
    return next((a for a in load_agents() if a.enabled and a.department == department), None)
