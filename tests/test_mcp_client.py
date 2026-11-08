import asyncio
from types import SimpleNamespace

import pytest

from ai_os import mcp_client


def test_mcp_destination_requires_exact_owner_allowlisted_hostname(monkeypatch):
    monkeypatch.setenv("AI_OS_MCP_ALLOWED_HOSTS", "mcp.example.org")
    monkeypatch.setattr(
        mcp_client.socket, "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    assert mcp_client._validate_destination("https://mcp.example.org/mcp") == "https://mcp.example.org/mcp"
    with pytest.raises(mcp_client.MCPDiscoveryError, match="not explicitly allowlisted"):
        mcp_client._validate_destination("https://other.example.org/mcp")


def test_mcp_destination_rejects_private_dns_resolution(monkeypatch):
    monkeypatch.setenv("AI_OS_MCP_ALLOWED_HOSTS", "mcp.example.org")
    monkeypatch.setattr(
        mcp_client.socket, "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    with pytest.raises(mcp_client.MCPDiscoveryError, match="non-public"):
        mcp_client._validate_destination("https://mcp.example.org/mcp")


@pytest.mark.parametrize("url", [
    "http://mcp.example.org/mcp",
    "https://user:pass@mcp.example.org/mcp",
    "https://mcp.example.org/mcp?token=secret",
    "https://mcp.example.org/mcp#fragment",
])
def test_mcp_destination_rejects_unsafe_url_forms(url):
    with pytest.raises(mcp_client.MCPDiscoveryError):
        mcp_client._validate_destination(url)


def test_remote_tool_metadata_is_marked_untrusted_and_not_executable():
    metadata = mcp_client._tool_metadata(SimpleNamespace(
        name="lookup", description="Remote tool",
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
    ))
    assert metadata["trust"] == "untrusted_remote_metadata"
    assert metadata["executable"] is False
    assert metadata["owner_approval_required_before_mapping"] is True


def test_remote_tool_schema_is_bounded():
    huge_schema = {"description": "x" * (mcp_client.MAX_SCHEMA_BYTES + 1)}
    with pytest.raises(mcp_client.MCPDiscoveryError, match="32 KiB"):
        mcp_client._tool_metadata(SimpleNamespace(
            name="large", description="", inputSchema=huge_schema,
        ))


def test_discovery_requires_enabled_mcp_endpoint(monkeypatch):
    from ai_os import control_plane

    monkeypatch.setattr(
        control_plane, "list_control_plane_endpoints",
        lambda: [{"endpoint_id": "ep", "protocol": "mcp", "enabled": False,
                  "base_url": "https://mcp.example.org/mcp", "name": "disabled",
                  "credential_ref": None}],
    )
    with pytest.raises(mcp_client.MCPDiscoveryError, match="explicitly enabled"):
        asyncio.run(mcp_client.discover_mcp_tools("ep"))


def test_vault_backed_bearer_credential_is_converted_to_authorization_header(monkeypatch):
    monkeypatch.setattr(
        "ai_os.credential_vault.resolve_credential",
        lambda ref: {"access_token": "test-token-value"},
    )
    headers = mcp_client._authorization_headers({
        "credential_ref": "vault:credential-123",
    })
    assert headers == {"Authorization": "Bearer test-token-value"}


def test_bearer_credential_rejects_non_vault_reference():
    with pytest.raises(mcp_client.MCPDiscoveryError, match="encrypted credential vault"):
        mcp_client._authorization_headers({"credential_ref": "plain-text-secret"})


def test_bearer_credential_rejects_missing_access_token(monkeypatch):
    monkeypatch.setattr(
        "ai_os.credential_vault.resolve_credential",
        lambda ref: {"api_key": "not-a-bearer-token"},
    )
    with pytest.raises(mcp_client.MCPDiscoveryError, match="access_token"):
        mcp_client._authorization_headers({"credential_ref": "vault:credential-123"})


def test_bearer_credential_rejects_header_injection(monkeypatch):
    monkeypatch.setattr(
        "ai_os.credential_vault.resolve_credential",
        lambda ref: {"access_token": "valid\r\nX-Injected: yes"},
    )
    with pytest.raises(mcp_client.MCPDiscoveryError, match="header characters"):
        mcp_client._authorization_headers({"credential_ref": "vault:credential-123"})



def test_mcp_oauth_client_credentials_uses_sdk_provider_and_allowlisted_issuer(monkeypatch):
    from mcp.client import auth as mcp_auth

    monkeypatch.setenv("AI_OS_MCP_ALLOWED_HOSTS", "mcp.example.org,auth.example.org")
    monkeypatch.setattr(
        mcp_client.socket, "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(
        "ai_os.credential_vault.resolve_credential",
        lambda ref: {
            "client_id": "client-123",
            "client_secret": "private-client-secret",
            "issuer": "https://auth.example.org/",
            "scope": "files:read profile",
            "token_endpoint_auth_method": "client_secret_basic",
        },
    )
    captured = {}

    class FakeOAuthProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(mcp_auth, "ClientCredentialsOAuthProvider", FakeOAuthProvider)
    endpoint = {"credential_ref": "vault:credential-123"}
    auth = mcp_client._oauth_client_auth(endpoint, "https://mcp.example.org/mcp")

    assert isinstance(auth, FakeOAuthProvider)
    assert captured["server_url"] == "https://mcp.example.org/mcp"
    assert captured["client_id"] == "client-123"
    assert captured["client_secret"] == "private-client-secret"
    assert captured["issuer"] == "https://auth.example.org/"
    assert captured["scope"] == "files:read profile"
    assert captured["token_endpoint_auth_method"] == "client_secret_basic"
    assert captured["storage"].get_tokens is not None


def test_mcp_oauth_client_credentials_rejects_unallowlisted_issuer(monkeypatch):
    monkeypatch.setenv("AI_OS_MCP_ALLOWED_HOSTS", "mcp.example.org")
    monkeypatch.setattr(
        "ai_os.credential_vault.resolve_credential",
        lambda ref: {
            "client_id": "client-123",
            "client_secret": "private-client-secret",
            "issuer": "https://untrusted-auth.example.net/",
        },
    )
    with pytest.raises(mcp_client.MCPDiscoveryError, match="issuer must be an HTTPS hostname"):
        mcp_client._oauth_client_auth(
            {"credential_ref": "vault:credential-123"},
            "https://mcp.example.org/mcp",
        )


def test_oauth_vault_payload_is_not_mistaken_for_static_bearer(monkeypatch):
    monkeypatch.setattr(
        "ai_os.credential_vault.resolve_credential",
        lambda ref: {
            "client_id": "client-123",
            "client_secret": "private-client-secret",
            "issuer": "https://auth.example.org/",
        },
    )
    assert mcp_client._authorization_headers({
        "credential_ref": "vault:credential-123",
    }) == {}


def test_mcp_oauth_client_credentials_rejects_bad_scope_type(monkeypatch):
    monkeypatch.setenv("AI_OS_MCP_ALLOWED_HOSTS", "mcp.example.org,auth.example.org")
    monkeypatch.setattr(
        mcp_client.socket, "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(
        "ai_os.credential_vault.resolve_credential",
        lambda ref: {
            "client_id": "client-123",
            "client_secret": "private-client-secret",
            "issuer": "https://auth.example.org/",
            "scope": ["files:read"],
        },
    )
    with pytest.raises(mcp_client.MCPDiscoveryError, match="scope must be"):
        mcp_client._oauth_client_auth(
            {"credential_ref": "vault:credential-123"},
            "https://mcp.example.org/mcp",
        )
