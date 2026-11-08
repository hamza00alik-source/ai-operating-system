"""API-key authentication for owner-operated deployments."""
import secrets
from fastapi import Header, HTTPException, status
from ai_os.config import get_settings


def _check_owner_key(expected: str, supplied: str | None) -> None:
    if not expected or not supplied or not secrets.compare_digest(supplied.strip(), expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid owner API key is required.",
            headers={"WWW-Authenticate": "ApiKey"})


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    settings = get_settings()
    if settings.environment == "development":
        return
    _check_owner_key(settings.api_key, x_api_key)


def require_owner_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Strict authentication for sensitive credential management, including development."""
    _check_owner_key(get_settings().api_key, x_api_key)
