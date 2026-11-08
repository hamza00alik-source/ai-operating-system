"""Built-in read-only tools exposed through the capability-gated agent tool gateway.

Adapters are registered by trusted application startup code. They never perform
publishing, writes, purchases, customer messaging, or payment actions.
"""
import asyncio

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


def _mcp_read(parameters: dict) -> dict:
    """Call one explicitly owner-mapped MCP tool through the read-only broker."""
    mapping_id = parameters.get("mapping_id")
    arguments = parameters.get("arguments", {})
    if not isinstance(mapping_id, str) or not mapping_id or len(mapping_id) > 120:
        raise ValueError("mapping_id must identify an owner-approved MCP mapping.")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object.")
    from ai_os.mcp_broker import (
        MCPBrokerError, get_mcp_tool_mapping, get_discovered_tool,
        validate_mcp_tool_arguments,
    )
    from ai_os.mcp_client import MCPDiscoveryError, call_mcp_read_only_tool

    mapping = get_mcp_tool_mapping(mapping_id)
    if mapping is None or not mapping["enabled"] or mapping["access_mode"] != "read_only":
        raise ValueError("MCP mapping is missing, disabled, or not read-only.")
    discovered = get_discovered_tool(mapping["endpoint_id"], mapping["tool_name"])
    if discovered is None:
        raise ValueError("MCP tool metadata is missing; owner must rediscover and review it.")
    validate_mcp_tool_arguments(discovered["input_schema"], arguments)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise ValueError("MCP read adapter must run in the supervised synchronous worker.")
    try:
        result = asyncio.run(call_mcp_read_only_tool(
            mapping["endpoint_id"], mapping["tool_name"], arguments,
            expected_schema=discovered["input_schema"],
        ))
    except (MCPBrokerError, MCPDiscoveryError) as exc:
        raise ValueError(str(exc)) from exc
    return {
        "mapping_id": mapping_id,
        "tool_name": mapping["tool_name"],
        "read_only_mapping": True,
        "result": result,
    }


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
    register_agent_tool_adapter(
        "mcp.read", capability="tool.mcp.read",
        adapter=_mcp_read,
    )
