"""Load the CEO and the complete pinned Agency Agents specialist library."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "agents" / "catalog.json"
AGENCY_ROOT = REPO_ROOT / "vendor" / "agency-agents"
DIVISIONS_PATH = AGENCY_ROOT / "divisions.json"

@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    department: str
    description: str
    capabilities: tuple[str, ...]
    requires_approval_for: tuple[str, ...]
    enabled: bool
    profile_path: str = ""
    tools: tuple[str, ...] = ()
    emoji: str = ""
    vibe: str = ""
    source: str = "local"

def _frontmatter(markdown: str) -> dict[str, str]:
    """Parse the simple scalar frontmatter fields used by Agency Agents."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", markdown, re.DOTALL)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values

def _capabilities(markdown: str) -> tuple[str, ...]:
    match = re.search(
        r"^##\s+(?:Core Capabilities|Core Competencies|Specialized Skills)\s*\n(.*?)(?=^##\s+|\Z)",
        markdown, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ("specialist_profile",)
    items = []
    for line in match.group(1).splitlines():
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            value = re.sub(r"\*\*([^*]+)\*\*", r"\1", bullet.group(1)).strip()
            if value:
                items.append(value[:120])
        if len(items) >= 12:
            break
    return tuple(items) or ("specialist_profile",)

def load_agent_profile(agent_id: str) -> str:
    agent = get_agent(agent_id)
    if agent is None:
        raise LookupError("Agent not found")
    if not agent.profile_path:
        return ""
    path = (AGENCY_ROOT / agent.profile_path).resolve()
    if AGENCY_ROOT.resolve() not in path.parents:
        raise ValueError("Invalid agent profile path")
    if not path.is_file():
        # Preserve the documented CEO-only fallback when a ZIP omits submodule contents.
        return ""
    return path.read_text(encoding="utf-8")

@lru_cache(maxsize=1)
def load_agents() -> tuple[AgentDefinition, ...]:
    payload: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported agent catalog schema_version")
    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list):
        raise ValueError("Agent catalog must contain an agents list")

    agents: list[AgentDefinition] = []
    seen: set[str] = set()
    # The locally-defined CEO is the sole owner-approval gateway.
    for raw in raw_agents:
        if raw.get("id") != "company-orchestrator":
            continue
        agent_id = raw["id"]
        seen.add(agent_id)
        agents.append(AgentDefinition(
            id=agent_id, name="CEO Agent", department="leadership",
            description=str(raw["description"]),
            capabilities=tuple(raw.get("capabilities", [])),
            requires_approval_for=tuple(raw.get("requires_approval_for", [])),
            enabled=True, profile_path=str(raw.get("profile_path", "")),
            source="ai-operating-system+agency-agents",
        ))

    if not DIVISIONS_PATH.exists():
        # A plain GitHub ZIP omits submodule contents; retain CEO-only fallback.
        return tuple(agents)

    division_data = json.loads(DIVISIONS_PATH.read_text(encoding="utf-8"))
    divisions = division_data.get("divisions", {})
    for department in sorted(divisions):
        directory = AGENCY_ROOT / department
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.md")):
            markdown = path.read_text(encoding="utf-8")
            meta = _frontmatter(markdown)
            if not meta.get("name") or not meta.get("description"):
                continue
            agent_id = path.stem
            if agent_id in seen:
                continue
            seen.add(agent_id)
            tools_value = meta.get("tools", "")
            agents.append(AgentDefinition(
                id=agent_id,
                name=meta["name"],
                department=department,
                description=meta["description"],
                capabilities=_capabilities(markdown),
                requires_approval_for=(),
                enabled=True,
                profile_path=path.relative_to(AGENCY_ROOT).as_posix(),
                tools=tuple(x.strip() for x in tools_value.split(",") if x.strip()),
                emoji=meta.get("emoji", ""),
                vibe=meta.get("vibe", ""),
                source="agency-agents",
            ))
    return tuple(agents)

def list_agents(*, enabled_only: bool = True) -> list[AgentDefinition]:
    return [agent for agent in load_agents() if agent.enabled or not enabled_only]

def get_agent(agent_id: str) -> AgentDefinition | None:
    return next((agent for agent in load_agents() if agent.id == agent_id), None)

def select_agent(department: str) -> AgentDefinition | None:
    return next((a for a in load_agents() if a.enabled and a.department == department), None)
