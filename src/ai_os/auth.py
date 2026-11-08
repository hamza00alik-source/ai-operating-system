"""API-key and persistent owner-session authentication."""
import hashlib
import secrets
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, Request, status

from ai_os.config import get_settings
from ai_os.db import connect

SESSION_COOKIE = "aios_owner_session"
SESSION_TTL_DAYS = 14


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
    # SameSite=Strict is the primary CSRF barrier; also validate Origin on unsafe cookie-authenticated requests.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("host", "")
        try:
            parsed_origin = urlsplit(origin or "")
        except ValueError:
            return False
        if not origin or parsed_origin.scheme != forwarded_proto or parsed_origin.netloc != host:
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
