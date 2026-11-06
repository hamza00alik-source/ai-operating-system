"""Server-side action execution boundary.

Adapters are registered only by trusted application code. There is no HTTP
registration or execution endpoint. External execution is disabled by default.
"""
import hashlib
import json
import os
from collections.abc import Callable
from typing import Any

from ai_os.approvals import ApprovalSecurityError, consume_owner_approval
from ai_os.audit import append_event
from ai_os.governance import OWNER_APPROVAL_ACTIONS


class ActionGatewayError(RuntimeError):
    """Raised when an approved action cannot safely reach its registered adapter."""


ActionAdapter = Callable[[dict, str], Any]
_ADAPTERS: dict[str, tuple[str, ActionAdapter]] = {}


def register_action_adapter(
    action_type: str,
    *,
    adapter_id: str,
    adapter: ActionAdapter,
) -> None:
    """Register a server-owned adapter during trusted application initialization."""
    normalized = action_type.strip().lower() if isinstance(action_type, str) else ""
    if normalized not in OWNER_APPROVAL_ACTIONS:
        raise ActionGatewayError("Adapter action is not in the owner-approval allowlist.")
    if not isinstance(adapter_id, str) or not adapter_id.strip() or len(adapter_id) > 120:
        raise ActionGatewayError("A valid server-owned adapter ID is required.")
    if not callable(adapter):
        raise ActionGatewayError("A callable server-owned adapter is required.")
    if normalized in _ADAPTERS:
        raise ActionGatewayError("An adapter is already registered for this action.")
    _ADAPTERS[normalized] = (adapter_id.strip(), adapter)


def clear_action_adapters_for_tests() -> None:
    """Clear in-process adapter registrations; intended for isolated tests only."""
    _ADAPTERS.clear()


def execute_approved_action(
    approval_id: str,
    *,
    action_type: str,
    parameters: dict,
    execution_id: str,
) -> dict:
    """Consume exact owner approval, then invoke only a registered trusted adapter.

    A missing adapter or disabled execution flag is checked before consuming the
    approval. Once consumed, an adapter failure is recorded and is never retried
    automatically; adapters must use execution_id for their own idempotency.
    """
    normalized = action_type.strip().lower() if isinstance(action_type, str) else ""
    if normalized not in OWNER_APPROVAL_ACTIONS:
        raise ActionGatewayError("Action is not in the owner-approval allowlist.")
    if os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() != "true":
        raise ActionGatewayError("External action execution is disabled.")
    registered = _ADAPTERS.get(normalized)
    if registered is None:
        raise ActionGatewayError("No trusted server-side adapter is registered for this action.")
    adapter_id, adapter = registered

    try:
        approval = consume_owner_approval(
            approval_id,
            action_type=normalized,
            parameters=parameters,
            execution_id=execution_id,
        )
    except ApprovalSecurityError as exc:
        raise ActionGatewayError(str(exc)) from exc

    scope = {
        "approval_id": approval_id,
        "execution_id": execution_id,
        "action_type": normalized,
        "action_hash": approval["action_hash"],
        "adapter_id": adapter_id,
    }
    append_event(
        "system:action-gateway", "approved_action_execution_started",
        "owner_approval_request", approval_id, scope,
    )
    try:
        result = adapter(parameters, execution_id)
        encoded = json.dumps(
            result, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False, default=str,
        )
        result_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        append_event(
            "system:action-gateway", "approved_action_execution_completed",
            "owner_approval_request", approval_id,
            {**scope, "result_sha256": result_hash},
        )
        return {
            "status": "completed",
            "approval_id": approval_id,
            "execution_id": execution_id,
            "adapter_id": adapter_id,
            "result": result,
            "result_sha256": result_hash,
        }
    except Exception as exc:
        append_event(
            "system:action-gateway", "approved_action_execution_failed",
            "owner_approval_request", approval_id,
            {**scope, "error_type": type(exc).__name__},
        )
        raise ActionGatewayError(
            "The approved action adapter failed after the approval was consumed. "
            "Inspect the audit trail before any manual retry."
        ) from exc
