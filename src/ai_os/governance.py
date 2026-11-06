"""Central CEO governance and owner-approval policy.

This module evaluates policy only. It does not execute tools or external actions.
"""
from ai_os.registry import get_agent

CEO_AGENT_ID = "company-orchestrator"

# Explicitly permitted internal work. Unknown actions fail closed.
INTERNAL_ACTIONS = {
    "research", "analyze", "draft", "plan", "assign_task",
    "create_work_packet", "test", "summarize", "update_internal_knowledge",
    "prepare_listing_draft", "prepare_content_draft", "review_metrics",
    "classify_support_request", "prepare_customer_reply_draft",
}

# Actions that always require the owner's explicit decision, requested by the CEO.
OWNER_APPROVAL_ACTIONS = {
    "publish_content", "publish_product", "publish_listing",
    "send_external_message", "send_marketing_campaign",
    "customer_commitment", "issue_refund", "spend_money",
    "purchase_service", "paid_promotion", "production_change",
    "deploy_public_service", "change_security_permissions",
    "modify_financial_settings", "create_paid_subscription", "create_website_draft",
}

def evaluate_action(agent_id: str, action: str) -> dict:
    """Return the policy decision for an enabled agent and a canonical action."""
    agent = get_agent(agent_id)
    if agent is None or not agent.enabled:
        return {
            "decision": "blocked_unknown_agent",
            "allowed": False,
            "owner_approval_required": False,
            "accountable_agent_id": CEO_AGENT_ID,
            "reason": "The requesting agent is not registered and enabled.",
        }

    normalized = action.strip().lower()
    if normalized in INTERNAL_ACTIONS:
        return {
            "decision": "allowed_internal",
            "allowed": True,
            "owner_approval_required": False,
            "accountable_agent_id": CEO_AGENT_ID,
            "reason": "Permitted internal work may proceed under CEO accountability.",
        }

    if normalized in OWNER_APPROVAL_ACTIONS:
        if agent_id != CEO_AGENT_ID:
            return {
                "decision": "escalate_to_ceo",
                "allowed": False,
                "owner_approval_required": True,
                "accountable_agent_id": CEO_AGENT_ID,
                "reason": "Only the CEO agent may submit this action for owner approval.",
            }
        return {
            "decision": "requires_owner_approval",
            "allowed": False,
            "owner_approval_required": True,
            "accountable_agent_id": CEO_AGENT_ID,
            "reason": "The CEO must present this action to the owner and wait for an explicit decision.",
        }

    return {
        "decision": "blocked_unknown_action",
        "allowed": False,
        "owner_approval_required": False,
        "accountable_agent_id": CEO_AGENT_ID,
        "reason": "This action is not on the internal allowlist or owner-approval list. CEO policy review is required.",
    }
