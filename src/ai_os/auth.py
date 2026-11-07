"""API-key authentication for owner-operated deployments."""
import secrets

from fastapi import Header, HTTPException, status

from ai_os.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Require the configured owner key outside local development."""
    settings = get_settings()
    if settings.environment == "development":
        return
    expected = settings.api_key
    if not expected or not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
