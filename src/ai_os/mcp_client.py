"""Owner-triggered MCP discovery with optional vault-backed bearer authentication.

Remote tool metadata remains untrusted and non-executable. This implements
static bearer-token transport only; OAuth 2.1 discovery/refresh is separate.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
from urllib.parse import urlsplit


class MCPDiscoveryError(RuntimeError):
    """A configured MCP endpoint cannot be safely discovered."""


MAX_TOOLS = 50
MAX_SCHEMA_BYTES = 32 * 1024
MAX_DESCRIPTION_CHARS = 2000
MAX_SSE_EVENT_BYTES = 64 * 1024


def _endpoint(endpoint_id: str) -> dict:
    from ai_os.control_plane import list_control_plane_endpoints

    endpoint = next(
        (item for item in list_control_plane_endpoints()
         if item["endpoint_id"] == endpoint_id),
        None,
    )
    if endpoint is None:
        raise MCPDiscoveryError("MCP endpoint was not found.")
    if endpoint["protocol"] != "mcp":
        raise MCPDiscoveryError("Only MCP endpoints support MCP discovery.")
    if not endpoint["enabled"]:
        raise MCPDiscoveryError("MCP endpoint must be explicitly enabled by the owner.")
    return endpoint


def _validate_destination(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise MCPDiscoveryError("MCP discovery requires a clean HTTPS URL without embedded credentials, query, or fragment.")
    host = parsed.hostname.rstrip(".").lower()
    allowed = {
        item.strip().rstrip(".").lower()
        for item in os.getenv("AI_OS_MCP_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    if not allowed or host not in allowed:
        raise MCPDiscoveryError(
            "MCP host is not explicitly allowlisted. Set AI_OS_MCP_ALLOWED_HOSTS "
            "to the exact hostname before discovery."
        )
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise MCPDiscoveryError("MCP hostname could not be resolved.") from exc
    if not addresses:
        raise MCPDiscoveryError("MCP hostname resolved to no addresses.")
    for address in {entry[4][0] for entry in addresses}:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise MCPDiscoveryError("MCP hostname resolves to a non-public address; discovery was blocked.")
    return url


def _resolve_endpoint_credential(endpoint: dict) -> dict | None:
    credential_ref = endpoint.get("credential_ref")
    if not credential_ref:
        return None
    if not isinstance(credential_ref, str) or not credential_ref.startswith("vault:"):
        raise MCPDiscoveryError("MCP credential reference must point to the encrypted credential vault.")
    try:
        from ai_os.credential_vault import CredentialVaultError, resolve_credential
        secret = resolve_credential(credential_ref)
    except (CredentialVaultError, ValueError) as exc:
        raise MCPDiscoveryError("MCP credential is unavailable, revoked, or cannot be decrypted.") from exc
    return secret


def _authorization_headers(endpoint: dict) -> dict[str, str]:
    """Resolve a static bearer token; OAuth client credentials use an httpx2 auth provider."""
    secret = _resolve_endpoint_credential(endpoint)
    if secret is None:
        return {}
    token = secret.get("access_token")
    if token is None and {"client_id", "client_secret", "issuer"}.issubset(secret):
        return {}
    if not isinstance(token, str) or not token.strip() or len(token) > 8192:
        raise MCPDiscoveryError(
            "Credential must contain access_token or OAuth client_id, client_secret and issuer."
        )
    if any(ord(char) < 33 or ord(char) > 126 for char in token):
        raise MCPDiscoveryError("Bearer credential contains invalid header characters.")
    return {"Authorization": "Bearer " + token}


class _EphemeralOAuthTokenStorage:
    """Keep short-lived client-credentials tokens in memory for one connection."""

    def __init__(self):
        self.tokens = None
        self.client_info = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        return self.client_info

    async def set_client_info(self, client_info):
        self.client_info = client_info


def _oauth_client_auth(endpoint: dict, server_url: str):
    """Build SDK OAuth 2.1 client-credentials auth from an encrypted vault record."""
    secret = _resolve_endpoint_credential(endpoint)
    if secret is None or secret.get("access_token") is not None:
        return None
    client_id = secret.get("client_id")
    client_secret = secret.get("client_secret")
    issuer = secret.get("issuer")
    scope = secret.get("scope", "")
    auth_method = secret.get("token_endpoint_auth_method", "client_secret_basic")
    if not all(isinstance(value, str) and value.strip() for value in (client_id, client_secret, issuer)):
        raise MCPDiscoveryError("OAuth credential requires non-empty client_id, client_secret and issuer.")
    if len(client_id) > 512 or len(client_secret) > 8192 or len(scope) > 1000:
        raise MCPDiscoveryError("OAuth client credential fields exceed their safety limits.")
    if any(ord(char) < 32 or ord(char) == 127 for char in client_id + client_secret + scope):
        raise MCPDiscoveryError("OAuth client credential contains control characters.")
    if not isinstance(scope, str):
        raise MCPDiscoveryError("OAuth scope must be a space-separated string.")
    if auth_method not in {"client_secret_basic", "client_secret_post"}:
        raise MCPDiscoveryError("Unsupported OAuth token endpoint authentication method.")
    # The authorization server is a separate network destination. It must be
    # HTTPS, publicly routable, and explicitly allowlisted just like the MCP host.
    try:
        _validate_destination(issuer)
    except MCPDiscoveryError as exc:
        raise MCPDiscoveryError("OAuth issuer must be an HTTPS hostname in AI_OS_MCP_ALLOWED_HOSTS.") from exc
    try:
        from mcp.client.auth import ClientCredentialsOAuthProvider
    except ImportError as exc:
        raise MCPDiscoveryError("Installed MCP SDK does not provide OAuth client-credentials support.") from exc
    try:
        return ClientCredentialsOAuthProvider(
            server_url=server_url,
            client_id=client_id,
            client_secret=client_secret,
            issuer=issuer,
            scope=scope,
            storage=_EphemeralOAuthTokenStorage(),
            token_endpoint_auth_method=auth_method,
        )
    except Exception as exc:
        raise MCPDiscoveryError("OAuth client-credentials configuration was rejected by the MCP SDK.") from exc


def _tool_metadata(tool) -> dict:
    name = getattr(tool, "name", None)
    if not isinstance(name, str) or not name or len(name) > 120:
        raise MCPDiscoveryError("MCP server returned a tool with an invalid name.")
    description = getattr(tool, "description", None)
    if description is not None and not isinstance(description, str):
        description = str(description)
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = {"type": "object", "properties": {}}
    if not isinstance(schema, dict):
        raise MCPDiscoveryError("MCP tool input schema must be a JSON object.")
    try:
        encoded = json.dumps(schema, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise MCPDiscoveryError("MCP tool input schema is not valid JSON.") from exc
    if len(encoded.encode("utf-8")) > MAX_SCHEMA_BYTES:
        raise MCPDiscoveryError("MCP tool input schema exceeds the 32 KiB limit.")
    return {
        "name": name,
        "description": (description or "")[:MAX_DESCRIPTION_CHARS],
        "input_schema": schema,
        "trust": "untrusted_remote_metadata",
        "executable": False,
        "owner_approval_required_before_mapping": True,
    }


async def discover_mcp_tools(endpoint_id: str) -> dict:
    """Discover bounded metadata from one owner-enabled, allowlisted MCP server."""
    endpoint = _endpoint(endpoint_id)
    url = _validate_destination(endpoint["base_url"])
    headers = _authorization_headers(endpoint)
    try:
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        import httpx2
    except ImportError as exc:
        raise MCPDiscoveryError(
            "MCP SDK is not installed. Install the optional dependency with: "
            "pip install -e '.[mcp]'"
        ) from exc

    try:
        timeout = httpx2.Timeout(30.0, read=60.0)
        oauth_auth = _oauth_client_auth(endpoint, url)
        async with httpx2.AsyncClient(
            headers=headers, auth=oauth_auth, timeout=timeout, follow_redirects=False
        ) as http_client:
            transport = streamable_http_client(
                url, http_client=http_client,
                max_sse_event_size=MAX_SSE_EVENT_BYTES,
            )
            async with Client(transport) as client:
                result = await asyncio.wait_for(client.list_tools(), timeout=20)
    except asyncio.TimeoutError as exc:
        raise MCPDiscoveryError("MCP discovery timed out after 20 seconds.") from exc
    except MCPDiscoveryError:
        raise
    except Exception as exc:
        raise MCPDiscoveryError(
            "MCP discovery failed. Check endpoint, TLS, bearer credential and server protocol."
        ) from exc

    remote_tools = list(getattr(result, "tools", []) or [])
    if len(remote_tools) > MAX_TOOLS:
        raise MCPDiscoveryError("MCP server returned more than 50 tools; discovery was rejected.")
    tools = [_tool_metadata(item) for item in remote_tools]
    names = [item["name"] for item in tools]
    if len(names) != len(set(names)):
        raise MCPDiscoveryError("MCP server returned duplicate tool names.")
    return {
        "endpoint_id": endpoint_id,
        "server_name": endpoint["name"],
        "discovered_tool_count": len(tools),
        "tools": tools,
        "authenticated": bool(headers or oauth_auth),
        "authentication_method": (
            "oauth_client_credentials" if oauth_auth
            else "static_bearer" if headers else "none"
        ),
        "execution_enabled": False,
        "notice": (
            "Discovery only. Remote descriptions and schemas are untrusted data; "
            "no tool has been granted a capability or made executable. Static bearer "
            "authentication does not implement OAuth authorization-code, refresh, or scopes."
        ),
    }



async def call_mcp_read_only_tool(
    endpoint_id: str, tool_name: str, arguments: dict,
    expected_schema: dict,
) -> dict:
    """Call one mapped remote tool; caller must enforce owner mapping and capability."""
    endpoint = _endpoint(endpoint_id)
    url = _validate_destination(endpoint["base_url"])
    headers = _authorization_headers(endpoint)
    if not isinstance(arguments, dict):
        raise MCPDiscoveryError("MCP tool arguments must be a JSON object.")
    try:
        encoded = json.dumps(arguments, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise MCPDiscoveryError("MCP tool arguments must be valid JSON.") from exc
    if len(encoded.encode("utf-8")) > MAX_SCHEMA_BYTES:
        raise MCPDiscoveryError("MCP tool arguments exceed the 32 KiB limit.")
    try:
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        import httpx2
    except ImportError as exc:
        raise MCPDiscoveryError("MCP SDK is not installed; install the optional [mcp] dependency.") from exc

    try:
        timeout = httpx2.Timeout(30.0, read=60.0)
        oauth_auth = _oauth_client_auth(endpoint, url)
        async with httpx2.AsyncClient(
            headers=headers, auth=oauth_auth, timeout=timeout, follow_redirects=False
        ) as http_client:
            transport = streamable_http_client(
                url, http_client=http_client,
                max_sse_event_size=MAX_SSE_EVENT_BYTES,
            )
            async with Client(transport) as client:
                available = await asyncio.wait_for(client.list_tools(), timeout=20)
                current = next(
                    (item for item in (getattr(available, "tools", []) or [])
                     if getattr(item, "name", None) == tool_name),
                    None,
                )
                if current is None:
                    raise MCPDiscoveryError("Approved remote MCP tool is no longer advertised.")
                current_schema = _tool_metadata(current)["input_schema"]
                if json.dumps(current_schema, sort_keys=True, separators=(",", ":")) != json.dumps(
                    expected_schema, sort_keys=True, separators=(",", ":")
                ):
                    raise MCPDiscoveryError(
                        "Remote MCP tool schema changed after owner approval; rediscover and review it."
                    )
                result = await asyncio.wait_for(
                    client.call_tool(tool_name, arguments), timeout=45
                )
    except asyncio.TimeoutError as exc:
        raise MCPDiscoveryError("MCP tool call timed out after 45 seconds.") from exc
    except Exception as exc:
        raise MCPDiscoveryError(
            "MCP tool call failed. Check endpoint, TLS, authentication and tool schema."
        ) from exc

    if bool(getattr(result, "isError", False)):
        raise MCPDiscoveryError("Remote MCP tool reported an error.")
    content = []
    for item in list(getattr(result, "content", []) or []):
        item_type = getattr(item, "type", "")
        if item_type != "text":
            raise MCPDiscoveryError(
                "Broker currently accepts text-only tool results; binary or embedded resources are blocked."
            )
        value = getattr(item, "text", "")
        if not isinstance(value, str):
            raise MCPDiscoveryError("Remote MCP tool returned an invalid text block.")
        content.append(value[:16_000])
    structured = getattr(result, "structuredContent", None)
    response = {"content": content}
    if structured is not None:
        try:
            json.dumps(structured, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise MCPDiscoveryError("Remote structured content is not valid JSON.") from exc
        response["structured_content"] = structured
    if len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > 64 * 1024:
        raise MCPDiscoveryError("Remote tool result exceeds the 64 KiB response limit.")
    return response
