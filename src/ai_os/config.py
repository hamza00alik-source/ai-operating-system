"""Environment-backed application configuration."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite:///./ai_os.db"
    api_key: str = ""


def get_settings() -> Settings:
    return Settings(
        environment=os.getenv("AI_OS_ENV", "development").strip().lower(),
        database_url=os.getenv("AI_OS_DATABASE_URL", "sqlite:///./ai_os.db"),
        api_key=os.getenv("AI_OS_API_KEY", ""),
    )
