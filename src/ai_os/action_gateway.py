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
from ai_os.control_plane import evaluate_capability, get_effective_agent, BROKER_CAPABILITIES


class ActionGatewayError(RuntimeError):
    """Raised when an approved action cannot safely reach its registered adapter."""


ActionAdapter = Callable[[dict, str], Any]
AgentToolAdapter = Callable[[dict], Any]
_AGENT_TOOL_ADAPTERS: dict[str, tuple[str, AgentToolAdapter]] = {}
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
        existing_id, _ = _ADAPTERS[normalized]
        if existing_id == adapter_id.strip():
            return
        raise ActionGatewayError("A different adapter is already registered for this action.")
    _ADAPTERS[normalized] = (adapter_id.strip(), adapter)


def clear_action_adapters_for_tests() -> None:
    """Clear in-process adapter registrations; intended for isolated tests only."""
    _ADAPTERS.clear()
    _AGENT_TOOL_ADAPTERS.clear()


def get_action_gateway_status() -> dict:
    """Report effective execution readiness without exposing adapter callables."""
    configured = sorted(_ADAPTERS)
    enabled = os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() == "true"
    return {
        "enabled": bool(enabled and configured),
        "flag_enabled": enabled,
        "adapter_count": len(configured),
        "registered_actions": configured,
        "external_actions_available": bool(enabled and configured),
        "agent_tool_count": len(_AGENT_TOOL_ADAPTERS),
        "agent_tool_calls_enabled": os.getenv("AI_OS_AGENT_TOOL_CALLS_ENABLED", "false").strip().lower() == "true",
        "registered_agent_tools": sorted(_AGENT_TOOL_ADAPTERS),
        "agent_tool_dispatch_policy": "explicit_capability_grants",
        "note": "External readiness requires the explicit enable flag and a server-registered adapter. Agent tools additionally require an explicit scoped Control Plane grant.",
    }


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
    if not isinstance(parameters, dict):
        raise ActionGatewayError("Approved action parameters must be a JSON object.")
    try:
        parameter_json = json.dumps(
            parameters, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ActionGatewayError("Approved action parameters must contain JSON-safe values.") from exc
    if len(parameter_json.encode("utf-8")) > 65536:
        raise ActionGatewayError("Approved action parameters exceed the 64 KiB safety limit.")
    if not isinstance(execution_id, str) or not execution_id.strip() or len(execution_id) > 160:
        raise ActionGatewayError("A valid bounded execution ID is required.")
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
        if len(encoded.encode("utf-8")) > 65536:
            raise ActionGatewayError("Approved action result exceeds the 64 KiB safety limit.")
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



def register_agent_tool_adapter(
    tool_name: str,
    *,
    capability: str,
    adapter: AgentToolAdapter,
) -> None:
    """Register a trusted in-process tool adapter behind an explicit capability."""
    normalized = tool_name.strip().lower() if isinstance(tool_name, str) else ""
    required = capability.strip().lower() if isinstance(capability, str) else ""
    if not normalized or len(normalized) > 100 or any(ch.isspace() for ch in normalized):
        raise ActionGatewayError("A valid tool name is required.")
    if required not in BROKER_CAPABILITIES or not required.startswith("tool."):
        raise ActionGatewayError("Tool adapters require a supported tool.* capability.")
    if not callable(adapter):
        raise ActionGatewayError("A callable trusted tool adapter is required.")
    existing = _AGENT_TOOL_ADAPTERS.get(normalized)
    if existing and existing[0] != required:
        raise ActionGatewayError("Tool is already registered with a different capability.")
    _AGENT_TOOL_ADAPTERS[normalized] = (required, adapter)


def clear_agent_tool_adapters_for_tests() -> None:
    _AGENT_TOOL_ADAPTERS.clear()


def execute_agent_tool(agent_id: str, tool_name: str, parameters: dict) -> dict:
    """Execute a trusted tool only when the caller has an explicit scoped grant."""
    normalized = tool_name.strip().lower() if isinstance(tool_name, str) else ""
    registered = _AGENT_TOOL_ADAPTERS.get(normalized)
    if registered is None:
        raise ActionGatewayError("No trusted tool adapter is registered.")
    capability, adapter = registered
    if not isinstance(parameters, dict):
        raise ActionGatewayError("Agent tool parameters must be a JSON object.")
    try:
        parameter_json = json.dumps(parameters, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ActionGatewayError("Agent tool parameters must contain JSON-safe values.") from exc
    if len(parameter_json.encode("utf-8")) > 65536:
        raise ActionGatewayError("Agent tool parameters exceed the 64 KiB limit.")
    agent = get_effective_agent(agent_id)
    if agent is None:
        raise ActionGatewayError("Agent is not enabled in the Control Plane.")
    decision = evaluate_capability(agent_id, capability, agent.department)
    if not decision.get("allowed"):
        append_event(
            "agent:" + agent_id, "agent_tool_execution_denied", "agent_tool", normalized,
            {"capability": capability, "decision": decision.get("decision")},
        )
        raise ActionGatewayError("Agent tool capability was denied by Control Plane policy.")
    append_event(
        "agent:" + agent_id, "agent_tool_execution_started", "agent_tool", normalized,
        {"capability": capability, "grant_id": decision.get("grant_id")},
    )
    try:
        result = adapter(parameters)
        encoded = json.dumps(
            result, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False, default=str,
        )
        if len(encoded.encode("utf-8")) > 65536:
            raise ActionGatewayError("Agent tool result exceeds the 64 KiB safety limit.")
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        append_event(
            "agent:" + agent_id, "agent_tool_execution_completed", "agent_tool", normalized,
            {"capability": capability, "grant_id": decision.get("grant_id"),
             "result_sha256": digest},
        )
        return {"status": "completed", "tool": normalized, "result": result,
                "result_sha256": digest}
    except Exception as exc:
        append_event(
            "agent:" + agent_id, "agent_tool_execution_failed", "agent_tool", normalized,
            {"capability": capability, "error_type": type(exc).__name__},
        )
        raise ActionGatewayError("Trusted agent tool adapter failed; inspect the audit trail.") from exc



def list_available_agent_tools(agent_id: str) -> list[dict]:
    """List only registered tools whose capability is currently granted to this agent."""
    agent = get_effective_agent(agent_id)
    if agent is None:
        return []
    available = []
    for name, (capability, _) in sorted(_AGENT_TOOL_ADAPTERS.items()):
        decision = evaluate_capability(agent_id, capability, agent.department)
        if decision.get("allowed"):
            available.append({"name": name, "capability": capability})
    return available
