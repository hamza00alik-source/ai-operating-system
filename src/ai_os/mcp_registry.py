"""Read-only official MCP Registry discovery client."""
from __future__ import annotations
import json
from urllib.parse import urlencode
import httpx

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"
MAX_RESPONSE_BYTES = 1_000_000
MAX_LIMIT = 25

class MCPRegistryError(RuntimeError):
    """Registry query failed safely."""

def _normalize(payload: object) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("servers"), list):
        raise MCPRegistryError("The MCP registry returned an invalid server list.")
    items = []
    for record in payload["servers"][:MAX_LIMIT]:
        if not isinstance(record, dict):
            continue
        server = record.get("server")
        if not isinstance(server, dict):
            continue
        name = server.get("name")
        if not isinstance(name, str) or not name or len(name) > 200:
            continue
        repository = server.get("repository")
        repository_url = repository.get("url") if isinstance(repository, dict) else None
        website = server.get("websiteUrl")
        packages = server.get("packages")
        remotes = server.get("remotes")
        meta = record.get("_meta")
        official = meta.get("io.modelcontextprotocol.registry/official", {}) if isinstance(meta, dict) else {}
        items.append({
            "name": name,
            "title": str(server.get("title") or name)[:200],
            "description": str(server.get("description") or "")[:1000],
            "version": str(server.get("version") or "")[:100],
            "status": str(official.get("status") or "unknown")[:30] if isinstance(official, dict) else "unknown",
            "is_latest": bool(official.get("isLatest")) if isinstance(official, dict) else False,
            "repository_url": repository_url if isinstance(repository_url, str) and repository_url.startswith("https://") else None,
            "website_url": website if isinstance(website, str) and website.startswith("https://") else None,
            "package_count": len(packages) if isinstance(packages, list) else 0,
            "remote_transport_count": len(remotes) if isinstance(remotes, list) else 0,
            "trust": "unverified_registry_metadata",
            "installable": False,
            "execution_enabled": False,
        })
    metadata = payload.get("metadata")
    cursor = metadata.get("nextCursor") if isinstance(metadata, dict) else None
    return {"servers": items, "count": len(items), "has_more": bool(cursor),
            "notice": "Discovery metadata only. Inspect source, package, transport and permissions before any connection; nothing is installed or executable."}

async def search_official_registry(query: str, limit: int = 10, *, transport=None) -> dict:
    query = query.strip()
    if len(query) < 3:
        raise ValueError("Search query must contain at least three characters.")
    if len(query) > 100:
        raise ValueError("Search query must be 100 characters or fewer.")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError("Limit must be between 1 and 25.")
    params = urlencode({"search": query, "version": "latest", "limit": limit})
    url = f"{REGISTRY_URL}?{params}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False, transport=transport) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
        if response.status_code != 200:
            raise MCPRegistryError(f"Official MCP registry returned HTTP {response.status_code}.")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise MCPRegistryError("Official MCP registry response exceeded the 1 MB safety limit.")
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise MCPRegistryError("Official MCP registry returned invalid JSON.") from exc
        return _normalize(payload)
    except MCPRegistryError:
        raise
    except (httpx.HTTPError, OSError) as exc:
        raise MCPRegistryError("Official MCP registry is unavailable; no integration was changed.") from exc
