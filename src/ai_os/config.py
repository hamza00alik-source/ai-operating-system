"""Environment-backed application configuration."""
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite:///./ai_os.db"

def get_settings() -> Settings:
    return Settings(
        environment=os.getenv("AI_OS_ENV", "development"),
        database_url=os.getenv("AI_OS_DATABASE_URL", "sqlite:///./ai_os.db"),
    )
