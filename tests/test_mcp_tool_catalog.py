from datetime import datetime, timezone

import pytest

from ai_os.db import connect, initialize_database
from ai_os.mcp_tool_catalog import (
    get_discovered_tool_schema,
    persist_discovered_tools,
    validate_discovered_tool_arguments,
)


def _setup(monkeypatch, tmp_path, *, enabled=True):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'mcp-catalog.db'}")
    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """INSERT INTO mcp_servers
            (id,name,endpoint,transport,credential_env_json,capabilities_json,enabled,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            ("server-1", "Research MCP", "https://mcp.example.com/mcp",
             "streamable_http", "[]", '["search"]', int(enabled), now, now),
        )


def test_owner_discovery_persists_schema_and_fingerprint(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 3}},
        "required": ["query"],
        "additionalProperties": False,
    }
    saved = persist_discovered_tools("server-1", [
        {"name": "search", "description": "Read-only search", "input_schema": schema}
    ])
    assert saved["tool_count"] == 1
    assert len(saved["schema_fingerprints"]["search"]) == 64
    record = get_discovered_tool_schema("server-1", "search")
    assert record["schema"] == schema
    assert record["schema_sha256"] == saved["schema_fingerprints"]["search"]


def test_proposal_arguments_must_match_persisted_schema(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    persist_discovered_tools("server-1", [{
        "name": "search",
        "input_schema": {
            "type": "object", "properties": {"query": {"type": "string"}},
            "required": ["query"], "additionalProperties": False,
        },
    }])
    digest = validate_discovered_tool_arguments("server-1", "search", {"query": "market"})
    assert len(digest) == 64
    with pytest.raises(ValueError, match="JSON Schema"):
        validate_discovered_tool_arguments("server-1", "search", {"query": "market", "admin": True})


def test_schema_discovery_rejects_external_references(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="references"):
        persist_discovered_tools("server-1", [{
            "name": "unsafe",
            "input_schema": {"$ref": "https://attacker.example/schema.json"},
        }])


def test_schema_discovery_rejects_missing_or_null_input_schema(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    persist_discovered_tools("server-1", [{"name": "search", "input_schema": {"type": "object"}}])
    for tool in ({"name": "missing"}, {"name": "null", "input_schema": None}):
        with pytest.raises(ValueError, match="missing a valid input_schema"):
            persist_discovered_tools("server-1", [tool])
    # A failed catalogue refresh must not erase the previously reviewed catalogue.
    assert get_discovered_tool_schema("server-1", "search")["schema"] == {"type": "object"}


def test_disabled_server_schema_is_not_usable(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, enabled=False)
    with pytest.raises(ValueError, match="enabled"):
        persist_discovered_tools("server-1", [{"name": "search", "input_schema": {"type": "object"}}])
    assert get_discovered_tool_schema("server-1", "search") is None
