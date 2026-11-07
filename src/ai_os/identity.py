"""Server-side signed identities for internal agent execution.

Tokens are short-lived, run-bound capabilities for trusted runtime handoffs.
Never expose them through public endpoints, model prompts, logs, or work packets.
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
MAX_CAPABILITIES = 20
CEO_AGENT_ID = "company-orchestrator"

# Runtime capabilities are granted by server policy, never by a caller's request.
AGENT_CAPABILITY_POLICY = {
    CEO_AGENT_ID: frozenset({"approval.request"}),
    "*": frozenset({"step.report"}),
}


class AgentIdentityError(ValueError):
    """Raised when an internal agent identity cannot be trusted."""


@dataclass(frozen=True)
class AgentPrincipal:
    """Verified, immutable identity passed between trusted runtime components."""

    agent_id: str
    run_id: str
    capabilities: tuple[str, ...]
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


def issue_agent_token(
    agent_id: str,
    *,
    run_id: str,
    capabilities: tuple[str, ...] | list[str],
    ttl_seconds: int = 120,
) -> str:
    """Mint a token only after resolving an enabled agent from the server registry."""
    if not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 120:
        raise AgentIdentityError("A valid server-resolved agent ID is required.")
    if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 120:
        raise AgentIdentityError("A valid company run ID is required.")
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= MAX_TOKEN_TTL_SECONDS:
        raise AgentIdentityError("Agent token lifetime must be between 1 and 300 seconds.")
    if not isinstance(capabilities, (tuple, list)) or not 1 <= len(capabilities) <= MAX_CAPABILITIES:
        raise AgentIdentityError("One to 20 explicit capabilities are required.")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 80 for item in capabilities):
        raise AgentIdentityError("Capabilities must be non-empty strings of at most 80 characters.")
    normalized = tuple(sorted(set(capabilities)))
    if len(normalized) != len(capabilities):
        raise AgentIdentityError("Capabilities must be unique.")

    from ai_os.registry import get_agent
    registered = get_agent(agent_id)
    if registered is None or not registered.enabled:
        raise AgentIdentityError("Only enabled server-registered agents may receive identities.")
    from ai_os.control_plane import is_control_plane_agent_enabled
    if not is_control_plane_agent_enabled(agent_id, fallback_enabled=registered.enabled):
        raise AgentIdentityError("Only enabled server-registered agents may receive identities.")
    allowed = AGENT_CAPABILITY_POLICY.get(agent_id, AGENT_CAPABILITY_POLICY["*"])
    if not set(normalized).issubset(allowed):
        raise AgentIdentityError("Requested capability is not granted to this agent by server policy.")

    now = int(time.time())
    claims = {
        "sub": agent_id,
        "run": run_id,
        "cap": list(normalized),
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
        "nonce": secrets.token_urlsafe(24),
    }
    encoded = _b64encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(_signing_key(), encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + _b64encode(signature)


def verify_agent_token(
    token: str,
    *,
    expected_agent_id: str | None = None,
    expected_run_id: str | None = None,
    required_capability: str | None = None,
) -> AgentPrincipal:
    """Verify signature, audience, expiry, run binding, and optional capability."""
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

    agent_id, run_id = claims.get("sub"), claims.get("run")
    capabilities = claims.get("cap")
    issued_at, expires_at, nonce = claims.get("iat"), claims.get("exp"), claims.get("nonce")
    if (
        not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 120
        or not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 120
        or not isinstance(capabilities, list) or not 1 <= len(capabilities) <= MAX_CAPABILITIES
        or any(not isinstance(item, str) or not item.strip() or len(item) > 80 for item in capabilities)
        or len(set(capabilities)) != len(capabilities)
        or not isinstance(issued_at, int) or isinstance(issued_at, bool)
        or not isinstance(expires_at, int) or isinstance(expires_at, bool)
        or not isinstance(nonce, str) or len(nonce) < 16
        or claims.get("aud") != AUDIENCE
    ):
        raise AgentIdentityError("Invalid agent identity claims.")

    allowed = AGENT_CAPABILITY_POLICY.get(agent_id, AGENT_CAPABILITY_POLICY["*"])
    if not set(capabilities).issubset(allowed):
        raise AgentIdentityError("Token contains a capability not granted by server policy.")

    from ai_os.registry import get_agent
    registered = get_agent(agent_id)
    if registered is None or not registered.enabled:
        raise AgentIdentityError("Agent is no longer registered and enabled.")
    from ai_os.control_plane import is_control_plane_agent_enabled
    if not is_control_plane_agent_enabled(agent_id, fallback_enabled=registered.enabled):
        raise AgentIdentityError("Agent is no longer registered and enabled.")

    now = int(time.time())
    if issued_at > now + CLOCK_SKEW_SECONDS:
        raise AgentIdentityError("Agent identity token was issued in the future.")
    if expires_at <= now or expires_at <= issued_at:
        raise AgentIdentityError("Agent identity token has expired.")
    if expires_at - issued_at > MAX_TOKEN_TTL_SECONDS:
        raise AgentIdentityError("Agent identity token lifetime exceeds the limit.")
    if expected_agent_id is not None and not hmac.compare_digest(agent_id, expected_agent_id):
        raise AgentIdentityError("Agent identity does not match the expected principal.")
    if expected_run_id is not None and not hmac.compare_digest(run_id, expected_run_id):
        raise AgentIdentityError("Agent identity is not bound to the expected run.")
    if required_capability is not None and required_capability not in capabilities:
        raise AgentIdentityError("Agent identity does not grant the required capability.")

    return AgentPrincipal(
        agent_id=agent_id,
        run_id=run_id,
        capabilities=tuple(capabilities),
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )


def consume_agent_token(
    token: str,
    *,
    expected_agent_id: str | None = None,
    expected_run_id: str | None = None,
    required_capability: str | None = None,
) -> AgentPrincipal:
    """Verify and atomically consume a token nonce; replay attempts fail closed."""
    principal = verify_agent_token(
        token,
        expected_agent_id=expected_agent_id,
        expected_run_id=expected_run_id,
        required_capability=required_capability,
    )
    from ai_os.db import connect
    try:
        with connect() as db:
            db.execute(
                "INSERT INTO consumed_agent_nonces(nonce,agent_id,run_id,expires_at) VALUES(?,?,?,?)",
                (principal.nonce, principal.agent_id, principal.run_id, principal.expires_at),
            )
    except Exception as exc:
        raise AgentIdentityError(
            "Agent identity token was already consumed or could not be recorded."
        ) from exc
    return principal
