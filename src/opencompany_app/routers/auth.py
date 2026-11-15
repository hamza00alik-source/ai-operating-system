"""Owner browser-session creation, restoration and revocation routes."""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from opencompany_app.api_schemas import OwnerLoginInput
from opencompany_app.api_dependencies import (
    _clear_login_failures,
    _login_retry_after,
    get_runtime,
    require_owner_key,
)
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


@router.post("/auth/session")
def create_owner_session(
    payload: OwnerLoginInput,
    request: Request,
    response: Response,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Exchange the owner API key for a revocable HttpOnly session cookie."""
    expected = os.environ.get("OPENCOMPANY_OWNER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner authentication is not configured.")
    client_key = request.client.host if request.client else "unknown"
    retry_after = _login_retry_after(client_key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many failed owner login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    if not hmac.compare_digest(payload.api_key, expected):
        retry_after = _login_retry_after(client_key, failed=True)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Too many failed owner login attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(status_code=401, detail="Owner authentication failed.")
    _clear_login_failures(client_key)
    token, csrf, expires = runtime.sessions.create(lifetime_hours=168)
    secure_cookie = os.environ.get("OPENCOMPANY_COOKIE_SECURE", "true").strip().lower() == "true"
    response.set_cookie(
        "opencompany_session", token, max_age=7 * 24 * 60 * 60, httponly=True,
        secure=secure_cookie, samesite="strict", path="/",
    )
    response.set_cookie(
        "opencompany_csrf", csrf, max_age=7 * 24 * 60 * 60, httponly=True,
        secure=secure_cookie, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "csrf_token": csrf, "expires_at": expires.isoformat()}


@router.get("/auth/session", dependencies=[Depends(require_owner_key)])
def owner_session_status(
    response: Response,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    opencompany_session: str | None = Cookie(default=None),
    opencompany_csrf: str | None = Cookie(default=None),
) -> dict:
    """Restore the same CSRF token across tabs; rotate only if its cookie is missing or invalid."""
    if not opencompany_session:
        raise HTTPException(status_code=401, detail="Owner browser session is missing.")
    renewed = runtime.sessions.rotate_csrf(opencompany_session, opencompany_csrf)
    if renewed is None:
        raise HTTPException(status_code=401, detail="Owner browser session has expired or been revoked.")
    csrf, expires = renewed
    secure_cookie = os.environ.get("OPENCOMPANY_COOKIE_SECURE", "true").strip().lower() == "true"
    response.set_cookie(
        "opencompany_csrf", csrf, max_age=7 * 24 * 60 * 60, httponly=True,
        secure=secure_cookie, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "authenticated": True, "session_type": "owner",
        "csrf_token": csrf, "expires_at": expires.isoformat(),
    }


@router.post("/auth/logout", dependencies=[Depends(require_owner_key)])
def revoke_owner_session(
    request: Request,
    response: Response,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    opencompany_session: str | None = Cookie(default=None),
) -> dict:
    if opencompany_session:
        runtime.sessions.revoke(opencompany_session)
    response.delete_cookie("opencompany_session", path="/", httponly=True, samesite="strict")
    response.delete_cookie("opencompany_csrf", path="/", httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False, "revoked": bool(opencompany_session)}


