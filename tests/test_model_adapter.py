import json
from types import SimpleNamespace

import pytest

from ai_os import model_adapter


def test_command_backend_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "command")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND", "agy")
    monkeypatch.delenv("AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED", raising=False)
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_ARGS", '["-p", "{prompt}", "--output-format", "json"]')
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    monkeypatch.setattr(model_adapter.shutil, "which", lambda value: "/usr/bin/agy")
    status = model_adapter.get_model_status()
    assert status["configured"] is False
    assert status["enabled"] is False
    assert status["reason"] == "disabled_by_default"
    assert status["backend"] == "command"
    assert status["execution_may_use_network"] is True


def test_command_args_require_prompt_placeholder(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_COMMAND", "agy")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED", "true")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_ARGS", '["--output-format", "json"]')
    with pytest.raises(ValueError, match="placeholder"):
        model_adapter._command_configuration()


def test_cli_json_parser_accepts_direct_object_and_response_envelope():
    expected = {"status": "completed", "summary": "Finished"}
    assert model_adapter._parse_json_object(json.dumps(expected)) == expected
    envelope = {"conversation_id": "opaque", "response": json.dumps(expected)}
    assert model_adapter._parse_json_object(json.dumps(envelope)) == expected


def test_cli_backend_uses_argv_without_shell_and_parses_output(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "command")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND", "agy")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED", "true")
    monkeypatch.setenv(
        "AI_OS_MODEL_COMMAND_ARGS",
        json.dumps(["-p", "{prompt}", "--output-format", "json"]),
    )
    monkeypatch.setenv("AI_OS_MODEL_NAME", "cli-managed")
    monkeypatch.setattr(model_adapter.shutil, "which", lambda value: "/usr/bin/agy")
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "conversation_id": "opaque",
                "response": json.dumps({"status": "completed", "summary": "CLI report"}),
            }),
            stderr="",
        )

    monkeypatch.setattr(model_adapter.subprocess, "run", fake_run)
    result, provider = model_adapter.generate_json("system policy", "do research")
    assert result == {"status": "completed", "summary": "CLI report"}
    assert provider["backend"] == "command"
    assert captured["argv"][0] == "/usr/bin/agy"
    assert "system policy" in captured["argv"][2]
    assert "do research" in captured["argv"][2]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stdin"] is model_adapter.subprocess.DEVNULL
    assert captured["kwargs"]["timeout"] <= 180


def test_cli_backend_rejects_nonzero_exit_without_exposing_stderr(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "command")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND", "agy")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED", "true")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_ARGS", '["-p", "{prompt}", "--output-format", "json"]')
    monkeypatch.setattr(model_adapter.shutil, "which", lambda value: "/usr/bin/agy")
    monkeypatch.setattr(
        model_adapter.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout="", stderr="private"),
    )
    with pytest.raises(RuntimeError, match="stderr was not exposed"):
        model_adapter.generate_json("system", "task")


def test_cli_backend_requires_no_tools_attestation_even_when_enabled(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "command")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND", "agy")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_ARGS", '["-p", "{prompt}", "--output-format", "json"]')
    monkeypatch.delenv("AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED", raising=False)
    monkeypatch.setattr(model_adapter.shutil, "which", lambda value: "/usr/bin/agy")
    status = model_adapter.get_model_status()
    assert status["configured"] is False
    assert status["enabled"] is False
    assert status["reason"] == "confirm_cli_no_tools"


def test_zero_cost_mode_blocks_configured_model_before_any_request(monkeypatch):
    monkeypatch.setenv("AI_OS_ZERO_COST_MODE", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "example-model")
    monkeypatch.setenv("AI_OS_MODEL_API_KEY", "test-secret")
    status = model_adapter.get_model_status()
    assert status["enabled"] is False
    assert status["configured"] is False
    assert status["reason"] == "zero_cost_mode"
    with pytest.raises(model_adapter.ModelNotConfigured, match="disabled or not configured"):
        model_adapter.generate_json("system", "task")


def test_zero_cost_mode_blocks_local_cli_too(monkeypatch):
    monkeypatch.setenv("AI_OS_ZERO_COST_MODE", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "command")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND", "some-local-model")
    status = model_adapter.get_model_status()
    assert status["enabled"] is False
    assert status["reason"] == "zero_cost_mode"
    with pytest.raises(model_adapter.ModelNotConfigured):
        model_adapter.generate_json("system", "task")
