"""API-key and persistent owner-session authentication."""
import hashlib
import os
import secrets
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, Request, status

from ai_os.config import get_settings
from ai_os.db import connect

SESSION_COOKIE = "aios_owner_session"
SESSION_TTL_DAYS = 14
DEFAULT_TRUSTED_ORIGINS = ("https://ai-operating-system-one.vercel.app",)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid owner session or API key is required.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def _check_owner_key(expected: str, supplied: str | None) -> None:
    if not expected or not supplied or not secrets.compare_digest(supplied.strip(), expected.strip()):
        raise _unauthorized()


def create_owner_session(supplied_key: str) -> tuple[str, str]:
    settings = get_settings()
    _check_owner_key(settings.api_key, supplied_key)
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SESSION_TTL_DAYS)
    with connect() as db:
        db.execute(
            "INSERT INTO owner_sessions(token_hash,created_at,expires_at,last_seen_at) VALUES(?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), now.isoformat(), expires.isoformat(), now.isoformat()),
        )
    return token, expires.isoformat()


def revoke_owner_session(token: str | None) -> None:
    if not token:
        return
    digest = hashlib.sha256(token.encode()).hexdigest()
    with connect() as db:
        db.execute("DELETE FROM owner_sessions WHERE token_hash=?", (digest,))


def _trusted_browser_origin(origin: str | None, request: Request) -> bool:
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    if parsed.scheme != forwarded_proto or not parsed.netloc:
        return False

    # Direct deployments may use their request host. Behind Vercel's rewrite proxy,
    # the upstream Host is Railway's hostname, so explicitly trust the production
    # dashboard origin instead of comparing it to that upstream Host header.
    request_hosts = {
        value.strip().lower()
        for value in (
            request.headers.get("host", ""),
            request.headers.get("x-forwarded-host", ""),
        )
        if value.strip()
    }
    if parsed.netloc.lower() in request_hosts:
        return True

    configured = os.getenv("AI_OS_TRUSTED_ORIGINS", "")
    trusted_origins = set(DEFAULT_TRUSTED_ORIGINS)
    trusted_origins.update(item.strip().rstrip("/") for item in configured.split(",") if item.strip())
    return origin.rstrip("/") in trusted_origins


def _valid_session(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        row = db.execute(
            "SELECT expires_at FROM owner_sessions WHERE token_hash=?", (digest,)
        ).fetchone()
        if row is None or row["expires_at"] <= now:
            db.execute("DELETE FROM owner_sessions WHERE token_hash=?", (digest,))
            return False
        db.execute("UPDATE owner_sessions SET last_seen_at=? WHERE token_hash=?", (now, digest))
    # SameSite=Strict plus an exact origin allowlist protects cookie-authenticated writes.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not _trusted_browser_origin(request.headers.get("origin"), request):
            return False
    return True


def _authenticate(request: Request, supplied: str | None, *, allow_development: bool) -> None:
    settings = get_settings()
    if allow_development and settings.environment == "development":
        return
    if supplied:
        _check_owner_key(settings.api_key, supplied)
        return
    if _valid_session(request):
        return
    raise _unauthorized()


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    _authenticate(request, x_api_key, allow_development=True)


def require_owner_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Strict authentication for sensitive owner operations, including development."""
    _authenticate(request, x_api_key, allow_development=False)
