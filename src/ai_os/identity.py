"""Server-side signed identities for internal agent execution.

Tokens are capabilities for in-process runtime handoffs, not user credentials.
Do not expose them through public endpoints, model prompts, logs, or work packets.
There is intentionally no HTTP token-issuance route.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

AUDIENCE = "ai-os-internal-agent"
MAX_TOKEN_TTL_SECONDS = 300
CLOCK_SKEW_SECONDS = 30


class AgentIdentityError(ValueError):
    """Raised when an internal agent identity cannot be trusted."""


@dataclass(frozen=True)
class AgentPrincipal:
    """Verified, immutable identity passed between trusted runtime components."""

    agent_id: str
    issued_at: int
    expires_at: int
    nonce: str
    audience: str = AUDIENCE


def _signing_key() -> bytes:
    configured = os.getenv("AI_OS_AGENT_SIGNING_KEY", "")
    if len(configured) < 32:
        raise AgentIdentityError(
            "AI_OS_AGENT_SIGNING_KEY must be configured with at least 32 characters."
        )
    return configured.encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    if not value or len(value) > 4096:
        raise AgentIdentityError("Malformed agent identity token.")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise AgentIdentityError("Malformed agent identity token.") from exc


def issue_agent_token(agent_id: str, *, ttl_seconds: int = 120) -> str:
    """Mint a short-lived token inside trusted server code only.

    Callers must resolve and authorize the agent from the server-side registry
    before calling this function. Never add a public endpoint around this helper.
    """
    if not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 120:
        raise AgentIdentityError("A valid server-resolved agent ID is required.")
    if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= MAX_TOKEN_TTL_SECONDS:
        raise AgentIdentityError("Agent token lifetime must be between 1 and 300 seconds.")

    now = int(time.time())
    claims = {
        "sub": agent_id,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
        "nonce": secrets.token_urlsafe(18),
    }
    encoded = _b64encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(_signing_key(), encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + _b64encode(signature)


def verify_agent_token(token: str, *, expected_agent_id: str | None = None) -> AgentPrincipal:
    """Verify signature, audience, lifetime, nonce, and optional expected identity."""
    if not isinstance(token, str) or len(token) > 8192 or token.count(".") != 1:
        raise AgentIdentityError("Malformed agent identity token.")
    encoded, supplied_signature = token.split(".", 1)
    expected_signature = hmac.new(
        _signing_key(), encoded.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected_signature, _b64decode(supplied_signature)):
        raise AgentIdentityError("Invalid agent identity signature.")

    try:
        claims = json.loads(_b64decode(encoded))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentIdentityError("Malformed agent identity claims.") from exc
    if not isinstance(claims, dict):
        raise AgentIdentityError("Malformed agent identity claims.")

    agent_id = claims.get("sub")
    issued_at = claims.get("iat")
    expires_at = claims.get("exp")
    nonce = claims.get("nonce")
    if (
        not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 120
        or not isinstance(issued_at, int) or isinstance(issued_at, bool)
        or not isinstance(expires_at, int) or isinstance(expires_at, bool)
        or not isinstance(nonce, str) or len(nonce) < 16
        or claims.get("aud") != AUDIENCE
    ):
        raise AgentIdentityError("Invalid agent identity claims.")

    now = int(time.time())
    if issued_at > now + CLOCK_SKEW_SECONDS:
        raise AgentIdentityError("Agent identity token was issued in the future.")
    if expires_at <= now or expires_at <= issued_at:
        raise AgentIdentityError("Agent identity token has expired.")
    if expires_at - issued_at > MAX_TOKEN_TTL_SECONDS:
        raise AgentIdentityError("Agent identity token lifetime exceeds the limit.")
    if expected_agent_id is not None and not hmac.compare_digest(agent_id, expected_agent_id):
        raise AgentIdentityError("Agent identity does not match the expected principal.")

    return AgentPrincipal(
        agent_id=agent_id,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
