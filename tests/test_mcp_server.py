import asyncio

import pytest


def test_opencompany_mcp_server_exposes_only_read_only_tools():
    pytest.importorskip("mcp")
    from mcp import Client
    from ai_os.mcp_server import build_mcp_server

    async def inspect_server():
        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools.tools}

    names = asyncio.run(inspect_server())
    assert {
        "get_company_status",
        "list_company_departments",
        "list_company_agents",
        "list_mcp_integrations",
    }.issubset(names)
    assert not any(
        any(word in name.lower() for word in ("publish", "delete", "refund", "send_payment"))
        for name in names
    )
