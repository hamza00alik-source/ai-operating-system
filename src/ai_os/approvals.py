"""Exact-scope, one-time owner approval primitives.

These functions deliberately have no HTTP routes yet. Callers must be trusted
server-side components. In particular, decide_owner_approval may only be called
from an owner-authenticated handler, and consume_owner_approval is not an
external-action executor.
"""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.governance import CEO_AGENT_ID, OWNER_APPROVAL_ACTIONS
from ai_os.identity import AgentIdentityError, consume_agent_token, verify_agent_token

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

    forbidden_fragments = ("password", "secret", "token", "api_key", "authorization",
                           "credential", "private_key", "access_key")
    def reject_credential_fields(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if isinstance(key, str) and any(fragment in key.lower() for fragment in forbidden_fragments):
                    raise ApprovalSecurityError("Approval parameters must reference connection IDs, never credentials or secrets.")
                reject_credential_fields(nested)
        elif isinstance(value, list):
            for nested in value:
                reject_credential_fields(nested)
    reject_credential_fields(parameters)
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
    # Validate the proposed action and referenced run before consuming the CEO credential.
    _, action_hash = canonical_action(action_type, parameters)
    try:
        preview = verify_agent_token(
            ceo_token,
            expected_agent_id=CEO_AGENT_ID,
            required_capability="approval.request",
        )
    except AgentIdentityError as exc:
        raise ApprovalSecurityError(str(exc)) from exc
    with connect() as db:
        run_exists = db.execute(
            "SELECT 1 FROM company_runs WHERE id=?", (preview.run_id,)
        ).fetchone()
    if not run_exists:
        raise ApprovalSecurityError("CEO approval request must reference an existing company run.")
    try:
        principal = consume_agent_token(
            ceo_token,
            expected_agent_id=CEO_AGENT_ID,
            expected_run_id=preview.run_id,
            required_capability="approval.request",
        )
    except AgentIdentityError as exc:
        raise ApprovalSecurityError(str(exc)) from exc
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
        "expires_at": now + ttl_seconds,
        "decided_at": None,
        "decision": None,
        "consumed_at": None,
        "execution_id": None,
    }
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
    expired = False
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
            expired = True
        if not expired and (not isinstance(action_hash, str) or not hmac.compare_digest(action_hash, row["action_hash"])):
            raise ApprovalSecurityError("Owner decision must reference the exact action hash shown for approval.")
        if expired:
            updated = None
        else:
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
    if expired:
        raise ApprovalSecurityError("Approval request has expired.")
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
    expired = False
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
            expired = True
        if not expired and not hmac.compare_digest(row["action_hash"], supplied_hash):
            raise ApprovalSecurityError("Execution parameters do not match the approved action.")
        if expired:
            consumed = None
        else:
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
    if expired:
        raise ApprovalSecurityError("Approval request has expired.")
    result = dict(consumed)
    result["parameters"] = json.loads(result.pop("parameters_json"))
    return result


def list_owner_approval_requests(*, status: str | None = None, limit: int = 100) -> list[dict]:
    """Return bounded approval inbox records with decoded exact-scope parameters."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Approval request limit must be between 1 and 500.")
    allowed_statuses = {"pending", "approved", "rejected", "consumed", "expired"}
    if status is not None and status not in allowed_statuses:
        raise ValueError("Unsupported approval request status.")
    query = "SELECT * FROM owner_approval_requests"
    parameters: list[object] = []
    if status is not None:
        query += " WHERE status=?"
        parameters.append(status)
    query += " ORDER BY created_at DESC,id DESC LIMIT ?"
    parameters.append(limit)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        db.execute(
            """UPDATE owner_approval_requests SET status='expired'
               WHERE status IN ('pending','approved') AND expires_at<=?""",
            (now,),
        )
        rows = db.execute(query, parameters).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["parameters"] = json.loads(item.pop("parameters_json"))
        results.append(item)
    return results
