"""Read-only live MCP discovery smoke test against a public no-auth server.

This script performs endpoint registration, owner activation, MCP initialize,
and tools/list only. It never calls a remote tool.
"""
import os
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="aios-mcp-smoke-") as temp_dir:
    os.environ["AI_OS_ENV"] = "development"
    os.environ["AI_OS_DATABASE_URL"] = f"sqlite:///{Path(temp_dir) / 'ai_os.db'}"
    os.environ["AI_OS_MCP_ALLOWED_HOSTS"] = "api.sondahub.com"

    from fastapi.testclient import TestClient
    from ai_os.api import app
    from ai_os import mcp_client
    if not callable(mcp_client._guard_outbound_request):
        raise RuntimeError("Outbound HTTPS allowlist guard is not installed.")

    try:
        with TestClient(app) as client:
            created = client.post(
                "/control-plane/endpoints",
                json={
                    "name": "Public MCP read-only discovery test",
                    "protocol": "mcp",
                    "base_url": "https://api.sondahub.com/mcp",
                },
            )
            if created.status_code != 201:
                raise RuntimeError(f"Endpoint registration failed: HTTP {created.status_code}")
            endpoint_id = created.json()["endpoint_id"]

            enabled = client.patch(
                f"/control-plane/endpoints/{endpoint_id}",
                json={"enabled": True},
            )
            if enabled.status_code != 200:
                raise RuntimeError(f"Endpoint activation failed: HTTP {enabled.status_code}")

            discovered = client.post(
                f"/control-plane/endpoints/{endpoint_id}/discover"
            )
            if discovered.status_code != 200:
                raise RuntimeError(
                    f"MCP discovery failed: HTTP {discovered.status_code}: "
                    f"{discovered.text[:250]}"
                )
            result = discovered.json()
            tools = result.get("tools", [])
            if not tools or result.get("discovered_tool_count", 0) < 1:
                raise RuntimeError("Public MCP server returned no tools.")
            if result.get("authenticated") is not False or result.get("authentication_method") != "none":
                raise RuntimeError("No-auth public MCP smoke test unexpectedly used credentials.")
            if result.get("execution_enabled") is not False:
                raise RuntimeError("Remote MCP tool execution must remain disabled.")
            if any(tool.get("executable") is not False for tool in tools):
                raise RuntimeError("Discovered remote tools were incorrectly marked executable.")

            print(
                "PASS: AIOS connected to the public MCP server and discovered "
                f"{len(tools)} tool definitions."
            )
            print("Verified: HTTPS allowlist, endpoint activation, MCP discovery and metadata-only safety.")
            print("No remote tools were invoked; no write or external action was attempted.")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit(
            f"Live MCP discovery smoke test failed: {type(exc).__name__}: {str(exc)[:300]}"
        ) from exc
