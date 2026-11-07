"""Load and validate the pinned Agency Agents team runbooks."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ai_os.registry import get_agent

RUNBOOKS_PATH = Path(__file__).resolve().parents[2] / "vendor" / "agency-agents" / "strategy" / "runbooks.json"

@lru_cache(maxsize=1)
def load_runbooks() -> tuple[dict, ...]:
    if not RUNBOOKS_PATH.exists():
        return ()
    payload = json.loads(RUNBOOKS_PATH.read_text(encoding="utf-8"))
    runbooks = payload.get("runbooks")
    if not isinstance(runbooks, list):
        raise ValueError("Agency Agents runbooks must contain a runbooks list")
    seen: set[str] = set()
    validated = []
    for runbook in runbooks:
        slug = runbook.get("slug")
        if not isinstance(slug, str) or not slug or slug in seen:
            raise ValueError("Runbook slugs must be non-empty and unique")
        seen.add(slug)
        groups = runbook.get("roster", [])
        for group in groups:
            for agent_id in group.get("agents", []):
                if get_agent(agent_id) is None:
                    raise ValueError(f"Runbook '{slug}' references unknown agent '{agent_id}'")
        validated.append(runbook)
    return tuple(validated)

def list_runbooks() -> list[dict]:
    return list(load_runbooks())

def get_runbook(slug: str) -> dict | None:
    return next((item for item in load_runbooks() if item["slug"] == slug), None)
