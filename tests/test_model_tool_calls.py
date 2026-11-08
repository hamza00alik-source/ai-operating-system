import json
from contextlib import contextmanager

import pytest

from ai_os import model_adapter


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def configure_model(monkeypatch, response):
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "test-model")
    monkeypatch.setattr(model_adapter, "urlopen", lambda *_args, **_kwargs: FakeResponse(response))


def test_generate_agent_turn_returns_structured_tool_call(monkeypatch):
    configure_model(monkeypatch, {"choices": [{"message": {
        "content": None,
        "tool_calls": [{"id": "call-1", "function": {
            "name": "search", "arguments": '{"query":"market"}'
        }}],
    }}]})
    result = model_adapter.generate_agent_turn("Research this", [{
        "name": "search", "description": "Search public information",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }])
    assert result == {"kind": "tool_call", "tool_name": "search",
                      "arguments": {"query": "market"}, "call_id": "call-1"}


def test_generate_agent_turn_returns_final_content(monkeypatch):
    configure_model(monkeypatch, {"choices": [{"message": {
        "content": "Research complete.", "tool_calls": []
    }}]})
    result = model_adapter.generate_agent_turn("Research this", [{
        "name": "search", "input_schema": {"type": "object", "properties": {}}
    }])
    assert result == {"kind": "final", "content": "Research complete."}


def test_generate_agent_turn_rejects_multiple_tool_calls(monkeypatch):
    configure_model(monkeypatch, {"choices": [{"message": {
        "content": None, "tool_calls": [
            {"function": {"name": "one", "arguments": "{}"}},
            {"function": {"name": "two", "arguments": "{}"}},
        ]
    }}]})
    with pytest.raises(RuntimeError, match="exactly one"):
        model_adapter.generate_agent_turn("Do work", [
            {"name": "one"}, {"name": "two"}
        ])


def test_generate_agent_turn_rejects_non_object_arguments(monkeypatch):
    configure_model(monkeypatch, {"choices": [{"message": {
        "content": None, "tool_calls": [{"function": {
            "name": "search", "arguments": '["not","an","object"]'
        }}]
    }}]})
    with pytest.raises(RuntimeError, match="JSON object"):
        model_adapter.generate_agent_turn("Do work", [{"name": "search"}])


def test_generate_agent_turn_sends_one_tool_and_disables_parallel_calls(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data))
        return FakeResponse({"choices": [{"message": {"content": "done"}}]})

    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "test-model")
    monkeypatch.setattr(model_adapter, "urlopen", fake_urlopen)
    model_adapter.generate_agent_turn("Do work", [{"name": "lookup"}])
    assert captured["tool_choice"] == "auto"
    assert captured["parallel_tool_calls"] is False
    assert len(captured["tools"]) == 1
