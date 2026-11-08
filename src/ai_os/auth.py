"""API-key authentication with distinct principals and role checks."""
from dataclasses import dataclass
import secrets

from fastapi import Depends, Header, HTTPException, status

from ai_os.config import get_settings

_VALID_ROLES = {"owner", "operator", "agent", "viewer"}


@dataclass(frozen=True)
class Principal:
    principal_id: str
    role: str


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> Principal:
    """Authenticate a caller and return its server-configured identity."""
    settings = get_settings()
    if settings.environment == "development":
        return Principal("local-development", "owner")

    candidates = dict(settings.api_keys)
    if settings.api_key:
        candidates.setdefault(settings.api_key, {"principal_id": "owner", "role": "owner"})
    matched = None
    supplied = x_api_key or ""
    # Compare against every configured key to avoid an early-exit key lookup.
    for token, identity in candidates.items():
        if secrets.compare_digest(supplied, token):
            matched = identity
    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    role = matched.get("role")
    principal_id = matched.get("principal_id")
    if role not in _VALID_ROLES or not isinstance(principal_id, str) or not principal_id.strip():
        raise HTTPException(status_code=500, detail="Configured API principal is invalid.")
    return Principal(principal_id=principal_id, role=role)


def require_roles(*allowed_roles: str):
    """Build a dependency that permits only the listed authenticated roles."""
    allowed = frozenset(allowed_roles)
    if not allowed or not allowed.issubset(_VALID_ROLES):
        raise ValueError("A valid set of roles is required.")

    def check_role(principal: Principal = Depends(require_api_key)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="This API key does not have permission for this action.")
        return principal

    return check_role


require_operator = require_roles("owner", "operator")
require_task_writer = require_roles("owner", "operator", "agent")
require_owner = require_roles("owner")
require_reader = require_roles("owner", "operator", "agent", "viewer")
