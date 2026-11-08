"""Environment-backed application configuration."""
from dataclasses import dataclass, field
import json
import os


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite:///./ai_os.db"
    api_key: str = ""
    api_keys: dict[str, dict[str, str]] = field(default_factory=dict)


def get_settings() -> Settings:
    raw_keys = os.getenv("AI_OS_API_KEYS", "").strip()
    try:
        api_keys = json.loads(raw_keys) if raw_keys else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI_OS_API_KEYS must contain a valid JSON object.") from exc
    if not isinstance(api_keys, dict):
        raise RuntimeError("AI_OS_API_KEYS must be a JSON object keyed by API key.")
    for key, principal in api_keys.items():
        if not isinstance(key, str) or not isinstance(principal, dict):
            raise RuntimeError("Each AI_OS_API_KEYS entry must map a key to a principal object.")
        if not isinstance(principal.get("principal_id"), str) or not principal["principal_id"].strip():
            raise RuntimeError("Each API key principal requires a non-empty principal_id.")
        if principal.get("role") not in {"owner", "operator", "agent", "viewer"}:
            raise RuntimeError("API key roles must be owner, operator, agent, or viewer.")
    return Settings(
        environment=os.getenv("AI_OS_ENV", "development").strip().lower(),
        database_url=os.getenv("AI_OS_DATABASE_URL", "sqlite:///./ai_os.db"),
        api_key=os.getenv("AI_OS_API_KEY", ""),
        api_keys=api_keys,
    )
