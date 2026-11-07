"""Small single-owner API-key gate. No accounts, cookies, or paid identity service."""
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

PUBLIC_PATHS = {"/health", "/dashboard"}
AGENT_AUTH_PATHS = {("POST", "/ceo/approval-requests")}
RUNTIME_AUTH_PATHS = {("POST", "/control-plane/runtime-heartbeat")}

async def authenticate_request(request: Request):
    """Require a configured owner token; fail closed for production misconfiguration."""
    configured = (os.getenv("AI_OS_API_TOKEN", "").strip() or os.getenv("AI_OS_API_KEY", "").strip())
    environment = os.getenv("AI_OS_ENV", "development").strip().lower()
    if request.url.path in PUBLIC_PATHS:
        request.state.actor = "system"
        return None

    # This single CEO ingress route performs its own signed-agent verification.
    # No other route may bypass the owner-token gate.
    if (request.method, request.url.path) in AGENT_AUTH_PATHS:
        request.state.actor = "unverified-agent"
        return None
    if (request.method, request.url.path) in RUNTIME_AUTH_PATHS:
        request.state.actor = "unverified-runtime"
        return None

    if not configured:
        if environment == "production":
            return JSONResponse(
                status_code=503,
                content={"detail": "Server authentication is not configured. Set AI_OS_API_TOKEN or AI_OS_API_KEY."},
            )
        request.state.actor = "local-development"
        return None

    if len(configured) < 32:
        return JSONResponse(
            status_code=503,
            content={"detail": "The configured owner API key must contain at least 32 characters."},
        )

    authorization = request.headers.get("authorization", "")
    supplied = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    if not supplied:
        supplied = request.headers.get("x-api-key", "").strip()

    if not supplied or not secrets.compare_digest(supplied, configured):
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
            content={"detail": "A valid owner bearer token is required."},
        )

    request.state.actor = "owner"
    return None
