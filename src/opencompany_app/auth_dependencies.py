"""Owner API-key and browser-session authentication dependencies."""
from __future__ import annotations

import hmac
import os
import time
from threading import Lock
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, Header, HTTPException, Request

from opencompany_app.runtime_dependencies import get_runtime
from opencompany_app.runtime import OpenCompanyRuntime


_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_LOCK = Lock()
_LOGIN_WINDOW_SECONDS = 900
_LOGIN_MAX_FAILURES = 5
_LOGIN_MAX_TRACKED_CLIENTS = 10_000


def _login_retry_after(client_key: str, *, failed: bool = False) -> int:
    now = time.monotonic()
    with _LOGIN_LOCK:
        for key, attempts in list(_LOGIN_FAILURES.items()):
            fresh = [stamp for stamp in attempts if now - stamp < _LOGIN_WINDOW_SECONDS]
            if fresh:
                _LOGIN_FAILURES[key] = fresh
            else:
                _LOGIN_FAILURES.pop(key, None)
        if client_key not in _LOGIN_FAILURES and len(_LOGIN_FAILURES) >= _LOGIN_MAX_TRACKED_CLIENTS:
            oldest_key = min(
                _LOGIN_FAILURES,
                key=lambda key: _LOGIN_FAILURES[key][-1] if _LOGIN_FAILURES[key] else now,
            )
            _LOGIN_FAILURES.pop(oldest_key, None)
        attempts = _LOGIN_FAILURES.setdefault(client_key, [])
        if failed:
            attempts.append(now)
        if len(attempts) < _LOGIN_MAX_FAILURES:
            return 0
        return max(1, int(_LOGIN_WINDOW_SECONDS - (now - attempts[0])))


def _clear_login_failures(client_key: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.pop(client_key, None)


def require_owner_key(
    request: Request,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    x_opencompany_api_key: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
    opencompany_session: str | None = Cookie(default=None),
) -> str:
    expected = os.environ.get("OPENCOMPANY_OWNER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    if opencompany_session:
        mutating = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
        if runtime.sessions.validate(
            opencompany_session, x_csrf_token, require_csrf=mutating
        ):
            # Browser sessions are same-origin only. SameSite cookies and a
            # session-bound CSRF token are required, and Origin must match Host.
            # API-key clients remain available for explicit server-to-server use.
            if mutating:
                origin = request.headers.get("origin")
                host = request.headers.get("host", "").casefold()
                try:
                    origin_parts = urlsplit(origin or "")
                    origin_host = origin_parts.netloc.casefold()
                    valid_origin = (
                        origin_parts.scheme in {"http", "https"}
                        and bool(origin_host)
                        and origin_host == host
                        and origin_parts.path in {"", "/"}
                        and not origin_parts.query
                        and not origin_parts.fragment
                    )
                except ValueError:
                    valid_origin = False
                if not valid_origin:
                    raise HTTPException(status_code=403, detail="Owner session requests must use the same origin.")
            return "owner"
    client_key = request.client.host if request.client else "unknown"
    if x_opencompany_api_key and hmac.compare_digest(x_opencompany_api_key, expected):
        _clear_login_failures(client_key)
        return "owner"
    if x_opencompany_api_key:
        retry_after = _login_retry_after(client_key, failed=True)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Too many failed owner authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    raise HTTPException(status_code=401, detail="Owner authentication failed.")
