"""Environment-backed application configuration."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    # Development-mode authentication bypass must be explicitly opted into.
    # An omitted deployment setting therefore fails closed.
    environment: str = "production"
    database_url: str = "sqlite:///./ai_os.db"
    api_key: str = ""


def get_settings() -> Settings:
    return Settings(
        environment=os.getenv("AI_OS_ENV", "production").strip().lower(),
        database_url=os.getenv("AI_OS_DATABASE_URL", "sqlite:///./ai_os.db"),
        api_key=os.getenv("AI_OS_API_KEY", ""),
    )
