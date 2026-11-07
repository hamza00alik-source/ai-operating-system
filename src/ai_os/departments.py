"""Read-only company department directory with live specialist resolution."""
import json
from functools import lru_cache
from pathlib import Path

from ai_os.registry import get_agent, list_agents

ROOT = Path(__file__).resolve().parents[2]
DEPARTMENTS_PATH = ROOT / "company" / "departments.json"


@lru_cache(maxsize=1)
def _load_config() -> dict:
    data = json.loads(DEPARTMENTS_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("departments"), list):
        raise ValueError("Unsupported or invalid department directory")
    ids = [item.get("id") for item in data["departments"]]
    if len(ids) != len(set(ids)) or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError("Department IDs must be unique non-empty strings")
    return data


def list_departments() -> list[dict]:
    config = _load_config()
    agents = list_agents()
    result = []
    for item in config["departments"]:
        lead = get_agent(item["manager_agent_id"])
        members = [agent for agent in agents if agent.department == item["id"]]
        result.append({
            **item,
            "manager": ({"id": lead.id, "name": lead.name, "source": lead.source}
                        if lead else None),
            "manager_available": lead is not None and lead.enabled,
            "specialist_count": len(members),
            "specialists": [{"id": agent.id, "name": agent.name}
                            for agent in members[:8]],
            "status": "partially_wired" if lead else "planned",
            "execution_enabled": False,
        })
    return result


def get_department(department_id: str) -> dict | None:
    return next((item for item in list_departments() if item["id"] == department_id), None)
