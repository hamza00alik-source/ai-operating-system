"""Exact-scope, one-time owner approval primitives.

These functions deliberately have no HTTP routes yet. Callers must be trusted
server-side components. In particular, decide_owner_approval may only be called
from an owner-authenticated handler, and consume_owner_approval is not an
external-action executor.
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.governance import CEO_AGENT_ID, OWNER_APPROVAL_ACTIONS
from ai_os.identity import AgentIdentityError, verify_agent_token

MAX_APPROVAL_TTL_SECONDS = 900
MAX_PARAMETERS_BYTES = 16_384


class ApprovalSecurityError(ValueError):
    """Raised when an approval scope or lifecycle check fails."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_action(action_type: str, parameters: dict) -> tuple[str, str]:
    """Return canonical JSON and SHA-256 hash for the exact action and arguments."""
    if not isinstance(action_type, str) or action_type.strip().lower() not in OWNER_APPROVAL_ACTIONS:
        raise ApprovalSecurityError("Action is not in the owner-approval allowlist.")
    if not isinstance(parameters, dict):
        raise ApprovalSecurityError("Action parameters must be a JSON object.")
    try:
        encoded = json.dumps(
            {"action_type": action_type.strip().lower(), "parameters": parameters},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ApprovalSecurityError("Action parameters must contain finite JSON values only.") from exc
    if len(encoded.encode("utf-8")) > MAX_PARAMETERS_BYTES:
        raise ApprovalSecurityError("Action parameters exceed the 16 KB limit.")
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return encoded, digest


def create_owner_approval_request(
    ceo_token: str,
    *,
    action_type: str,
    parameters: dict,
    ttl_seconds: int = MAX_APPROVAL_TTL_SECONDS,
) -> dict:
    """Create a pending request only from a signed CEO principal for its run."""
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= MAX_APPROVAL_TTL_SECONDS:
        raise ApprovalSecurityError("Approval lifetime must be between 1 and 900 seconds.")
    try:
        principal = verify_agent_token(
            ceo_token,
            expected_agent_id=CEO_AGENT_ID,
            required_capability="approval.request",
        )
    except AgentIdentityError as exc:
        raise ApprovalSecurityError(str(exc)) from exc

    canonical_json, action_hash = canonical_action(action_type, parameters)
    now = int(time.time())
    request = {
        "id": str(uuid4()),
        "run_id": principal.run_id,
        "requested_by": principal.agent_id,
        "action_type": action_type.strip().lower(),
        "parameters_json": json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False),
        "action_hash": action_hash,
        "status": "pending",
        "created_at": _now_iso(),
        "expires_at": min(principal.expires_at, now + ttl_seconds),
        "decided_at": None,
        "decision": None,
        "consumed_at": None,
        "execution_id": None,
    }
    if request["expires_at"] <= now:
        raise ApprovalSecurityError("CEO identity expires before the approval request can be created.")
    with connect() as db:
        db.execute(
            """INSERT INTO owner_approval_requests
            (id,run_id,requested_by,action_type,parameters_json,action_hash,status,
             created_at,expires_at,decided_at,decision,consumed_at,execution_id)
            VALUES (:id,:run_id,:requested_by,:action_type,:parameters_json,:action_hash,
                    :status,:created_at,:expires_at,:decided_at,:decision,:consumed_at,:execution_id)""",
            request,
        )
    return {key: value for key, value in request.items() if key != "parameters_json"} | {
        "parameters": json.loads(request["parameters_json"])
    }


def decide_owner_approval(
    approval_id: str,
    *,
    action_hash: str,
    decision: str,
) -> dict | None:
    """Record an owner decision; only call behind the owner-authenticated API boundary."""
    if decision not in {"approved", "rejected"}:
        raise ApprovalSecurityError("Owner decision must be approved or rejected.")
    now = int(time.time())
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM owner_approval_requests WHERE id=?", (approval_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "pending":
            raise ApprovalSecurityError("Approval is no longer pending.")
        if row["expires_at"] <= now:
            db.execute(
                "UPDATE owner_approval_requests SET status='expired' WHERE id=? AND status='pending'",
                (approval_id,),
            )
            raise ApprovalSecurityError("Approval request has expired.")
        if not isinstance(action_hash, str) or not hashlib.sha256(action_hash.encode()).digest() == hashlib.sha256(row["action_hash"].encode()).digest():
            raise ApprovalSecurityError("Owner decision must reference the exact action hash shown for approval.")
        decided_at = _now_iso()
        cursor = db.execute(
            """UPDATE owner_approval_requests SET status=?,decision=?,decided_at=?
               WHERE id=? AND status='pending' AND action_hash=?""",
            (decision, decision, decided_at, approval_id, action_hash),
        )
        if cursor.rowcount != 1:
            raise ApprovalSecurityError("Approval changed concurrently; reload and review it.")
        updated = db.execute(
            "SELECT * FROM owner_approval_requests WHERE id=?", (approval_id,)
        ).fetchone()
    result = dict(updated)
    result["parameters"] = json.loads(result.pop("parameters_json"))
    return result


def consume_owner_approval(
    approval_id: str,
    *,
    action_type: str,
    parameters: dict,
    execution_id: str,
) -> dict:
    """Atomically consume an approval only for the exact approved action, once."""
    if not isinstance(execution_id, str) or not execution_id.strip() or len(execution_id) > 120:
        raise ApprovalSecurityError("A valid execution ID is required.")
    _, supplied_hash = canonical_action(action_type, parameters)
    now = int(time.time())
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM owner_approval_requests WHERE id=?", (approval_id,)
        ).fetchone()
        if row is None:
            raise ApprovalSecurityError("Approval request not found.")
        if row["status"] != "approved":
            raise ApprovalSecurityError("Approval is not in the approved state.")
        if row["expires_at"] <= now:
            db.execute(
                "UPDATE owner_approval_requests SET status='expired' WHERE id=? AND status='approved'",
                (approval_id,),
            )
            raise ApprovalSecurityError("Approval request has expired.")
        if row["action_hash"] != supplied_hash:
            raise ApprovalSecurityError("Execution parameters do not match the approved action.")
        cursor = db.execute(
            """UPDATE owner_approval_requests
               SET status='consumed',consumed_at=?,execution_id=?
               WHERE id=? AND status='approved' AND action_hash=? AND expires_at>?""",
            (_now_iso(), execution_id, approval_id, supplied_hash, now),
        )
        if cursor.rowcount != 1:
            raise ApprovalSecurityError("Approval could not be consumed; it may have expired or been used.")
        consumed = db.execute(
            "SELECT * FROM owner_approval_requests WHERE id=?", (approval_id,)
        ).fetchone()
    result = dict(consumed)
    result["parameters"] = json.loads(result.pop("parameters_json"))
    return result
