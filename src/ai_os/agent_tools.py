"""Built-in read-only tools exposed through the capability-gated agent tool gateway.

Adapters are registered by trusted application startup code. They never perform
publishing, writes, purchases, customer messaging, or payment actions.
"""
from ai_os.action_gateway import register_agent_tool_adapter
from ai_os.free_research import collect_release_feed_candidates
from ai_os.knowledge import retrieve_accepted_knowledge
from ai_os.woocommerce import WooCommerceReadOnlyClient


def _query(parameters: dict) -> str:
    value = parameters.get("query")
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= 300:
        raise ValueError("query must contain 3 to 300 characters")
    return value.strip()


def _bounded_int(parameters: dict, name: str, default: int, minimum: int, maximum: int) -> int:
    value = parameters.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _research_release_feeds(parameters: dict) -> dict:
    query = _query(parameters)
    max_per_feed = _bounded_int(parameters, "max_per_feed", 5, 1, 5)
    results = collect_release_feed_candidates(query, max_per_feed=max_per_feed)
    return {"results": results, "count": len(results), "source_mode": "fixed_public_github_feeds"}


def _knowledge_search(parameters: dict) -> dict:
    query = _query(parameters)
    limit = _bounded_int(parameters, "limit", 5, 1, 10)
    results = retrieve_accepted_knowledge(query, limit=limit, max_content_chars=1200)
    return {"results": results, "count": len(results), "source_mode": "owner_accepted_company_knowledge"}


def _store_products(parameters: dict) -> dict:
    page = _bounded_int(parameters, "page", 1, 1, 100)
    per_page = _bounded_int(parameters, "per_page", 20, 1, 50)
    products = WooCommerceReadOnlyClient.from_environment().list_products(
        page=page, per_page=per_page
    )
    return {"products": products, "count": len(products), "read_only": True}


def _store_order_statuses(parameters: dict) -> dict:
    page = _bounded_int(parameters, "page", 1, 1, 100)
    per_page = _bounded_int(parameters, "per_page", 20, 1, 50)
    status = parameters.get("status")
    if status is not None and not isinstance(status, str):
        raise ValueError("status must be a string when supplied")
    orders = WooCommerceReadOnlyClient.from_environment().list_order_statuses(
        page=page, per_page=per_page, status=status
    )
    return {"orders": orders, "count": len(orders), "read_only": True,
            "customer_personal_data_included": False}


def register_builtin_agent_tools() -> None:
    """Idempotently register only the built-in bounded read-only adapters."""
    register_agent_tool_adapter(
        "research.release_feeds", capability="tool.research.read",
        adapter=_research_release_feeds,
    )
    register_agent_tool_adapter(
        "knowledge.search", capability="tool.knowledge.read",
        adapter=_knowledge_search,
    )
    register_agent_tool_adapter(
        "store.products.read", capability="tool.store.read",
        adapter=_store_products,
    )
    register_agent_tool_adapter(
        "store.orders.read", capability="tool.store.read",
        adapter=_store_order_statuses,
    )
