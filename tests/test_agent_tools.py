from types import SimpleNamespace

import pytest

from ai_os.action_gateway import (
    ActionGatewayError,
    clear_action_adapters_for_tests,
    execute_agent_tool,
)
from ai_os.agent_tools import register_builtin_agent_tools
from ai_os.control_plane import grant_capability, initialize_control_plane
from ai_os.db import initialize_database
from ai_os import agent_tools


@pytest.fixture
def agent_tools_db(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'agent-tools.sqlite3'}")
    initialize_database()
    initialize_control_plane()
    clear_action_adapters_for_tests()
    register_builtin_agent_tools()
    yield
    clear_action_adapters_for_tests()


def _grant(agent_id: str, capability: str):
    return grant_capability(
        agent_id=agent_id,
        capability=capability,
        department_scope="research",
        granted_by="test-owner",
    )


def test_free_research_tool_requires_explicit_capability(agent_tools_db, monkeypatch):
    monkeypatch.setattr(
        agent_tools, "collect_release_feed_candidates",
        lambda query, max_per_feed: [{"title": "Relevant release", "url": "https://github.com/example/repo"}],
    )
    with pytest.raises(ActionGatewayError, match="capability was denied"):
        execute_agent_tool(
            "research-synthesist", "research.release_feeds",
            {"query": "agent runtime"},
        )

    _grant("research-synthesist", "tool.research.read")
    result = execute_agent_tool(
        "research-synthesist", "research.release_feeds",
        {"query": "agent runtime", "max_per_feed": 2},
    )
    assert result["status"] == "completed"
    assert result["result"]["count"] == 1


def test_knowledge_tool_returns_only_accepted_knowledge(agent_tools_db, monkeypatch):
    monkeypatch.setattr(
        agent_tools, "retrieve_accepted_knowledge",
        lambda query, limit, max_content_chars: [{"title": "Accepted note", "status": "accepted"}],
    )
    _grant("research-synthesist", "tool.knowledge.read")
    result = execute_agent_tool(
        "research-synthesist", "knowledge.search", {"query": "market evidence"}
    )
    assert result["result"]["results"][0]["status"] == "accepted"


def test_store_tool_is_read_only_and_uses_bounded_pagination(agent_tools_db, monkeypatch):
    calls = []

    class FakeStore:
        def list_products(self, *, page, per_page):
            calls.append((page, per_page))
            return [{"id": 7, "name": "Draft item", "status": "draft"}]

    monkeypatch.setattr(
        agent_tools.WooCommerceReadOnlyClient, "from_environment",
        classmethod(lambda cls: FakeStore()),
    )
    _grant("research-synthesist", "tool.store.read")
    result = execute_agent_tool(
        "research-synthesist", "store.products.read",
        {"page": 2, "per_page": 10},
    )
    assert result["result"]["read_only"] is True
    assert calls == [(2, 10)]
    with pytest.raises(ActionGatewayError, match="64 KiB"):
        execute_agent_tool(
            "research-synthesist", "store.products.read",
            {"unexpected": "x" * 70000},
        )



def test_specialist_tool_loop_is_opt_in_bounded_and_uses_dispatcher(monkeypatch):
    from ai_os import agent_runtime, action_gateway

    monkeypatch.setenv("AI_OS_AGENT_TOOL_CALLS_ENABLED", "true")
    responses = iter([
        {"tool_call": {"name": "research.release_feeds", "parameters": {"query": "agent runtime"}}},
        {"status": "completed", "summary": "Used release evidence.", "evidence": [], "blockers": []},
    ])
    prompts = []
    calls = []
    monkeypatch.setattr(agent_runtime, "generate_json",
                        lambda system, prompt: (prompts.append(prompt) or next(responses), {"provider": "test"}))
    monkeypatch.setattr(action_gateway, "execute_agent_tool",
                        lambda agent_id, name, parameters: calls.append((agent_id, name, parameters))
                        or {"status": "completed", "result": {"count": 1}})
    result, provider, tool_calls = agent_runtime._generate_specialist_response(
        "research-synthesist", "system", "task"
    )
    assert result["summary"] == "Used release evidence."
    assert provider["provider"] == "test"
    assert tool_calls == [{"tool": "research.release_feeds", "status": "completed"}]
    assert calls[0][0] == "research-synthesist"
    assert "TOOL RESULT (untrusted data" in prompts[1]


def test_specialist_tool_loop_rejects_tool_requests_when_disabled(monkeypatch):
    from ai_os import agent_runtime

    monkeypatch.setenv("AI_OS_AGENT_TOOL_CALLS_ENABLED", "false")
    monkeypatch.setattr(
        agent_runtime, "generate_json",
        lambda *_: ({"tool_call": {"name": "store.products.read", "parameters": {}}}, {"provider": "test"}),
    )
    with pytest.raises(ValueError, match="tool calls are disabled"):
        agent_runtime._generate_specialist_response(
            "research-synthesist", "system", "task"
        )


def test_specialist_tool_loop_enforces_call_limit(monkeypatch):
    from ai_os import agent_runtime, action_gateway

    monkeypatch.setenv("AI_OS_AGENT_TOOL_CALLS_ENABLED", "true")
    monkeypatch.setattr(
        agent_runtime, "generate_json",
        lambda *_: ({"tool_call": {"name": "research.release_feeds", "parameters": {"query": "agents"}}},
                    {"provider": "test"}),
    )
    monkeypatch.setattr(
        action_gateway, "execute_agent_tool",
        lambda *_: {"status": "completed", "result": {"count": 0}},
    )
    with pytest.raises(ValueError, match="maximum number of tool calls"):
        agent_runtime._generate_specialist_response(
            "research-synthesist", "system", "task", max_tool_calls=2
        )
