"""Owner-approved WooCommerce product draft adapter.

The adapter only creates unpublished products after explicit owner approval.
It cannot publish, update, delete, refund, or alter store/payment settings.
"""
import os

from ai_os.action_gateway import register_action_adapter
from ai_os.woocommerce import WooCommerceReadOnlyClient


def register_woocommerce_draft_adapter() -> bool:
    enabled = (
        os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() == "true"
        and os.getenv("AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED", "false").strip().lower() == "true"
        and all(os.getenv(name, "").strip() for name in (
            "AI_OS_WOOCOMMERCE_URL",
            "AI_OS_WOOCOMMERCE_CONSUMER_KEY",
            "AI_OS_WOOCOMMERCE_CONSUMER_SECRET",
        ))
    )
    if not enabled:
        return False

    def create_draft(parameters: dict, execution_id: str) -> dict:
        if set(parameters) != {"name", "description", "regular_price"}:
            raise ValueError("Product draft action accepts only name, description, and regular_price.")
        client = WooCommerceReadOnlyClient.from_environment()
        result = client.create_product_draft(
            name=parameters["name"],
            description=parameters["description"],
            regular_price=parameters["regular_price"],
        )
        return {"execution_id": execution_id, "draft_product": result}

    register_action_adapter(
        "create_product_draft",
        adapter_id="woocommerce-create-unpublished-product-v1",
        adapter=create_draft,
    )
    return True
