import asyncio
import httpx
import pytest

from ai_os.mcp_registry import MCPRegistryError, search_official_registry


@pytest.mark.asyncio
def test_registry_search_returns_metadata_only():
    payload = {
        "servers": [{
            "server": {
                "name": "io.example/demo",
                "title": "Demo",
                "description": "Read-only demo",
                "version": "1.2.3",
                "repository": {"url": "https://github.com/example/demo"},
                "packages": [{"identifier": "demo"}],
            },
            "_meta": {"io.modelcontextprotocol.registry/official": {
                "status": "active", "isLatest": True
            }},
        }],
        "metadata": {"nextCursor": None},
    }

    def handler(request):
        assert request.url.host == "registry.modelcontextprotocol.io"
        assert request.url.params["search"] == "demo"
        assert request.url.params["version"] == "latest"
        return httpx.Response(200, json=payload)

    result = asyncio.run(search_official_registry("demo", transport=httpx.MockTransport(handler)))
    assert result["count"] == 1
    server = result["servers"][0]
    assert server["name"] == "io.example/demo"
    assert server["trust"] == "unverified_registry_metadata"
    assert server["installable"] is False
    assert server["execution_enabled"] is False


@pytest.mark.asyncio
def test_registry_search_rejects_short_query():
    with pytest.raises(ValueError, match="three characters"):
        asyncio.run(search_official_registry("ab"))


@pytest.mark.asyncio
def test_registry_search_rejects_non_200():
    def handler(request):
        return httpx.Response(503)

    with pytest.raises(MCPRegistryError, match="HTTP 503"):
        asyncio.run(search_official_registry("demo", transport=httpx.MockTransport(handler)))
