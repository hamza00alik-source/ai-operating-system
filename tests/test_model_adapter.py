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



def _enable_groq_free_only(monkeypatch, *, model="llama-3.3-70b-versatile"):
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_FREE_ONLY", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "openai_compatible")
    monkeypatch.setenv("AI_OS_MODEL_PROVIDER", "groq")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", model)
    monkeypatch.setenv("AI_OS_MODEL_API_KEY", "test-secret")
    monkeypatch.setenv("AI_OS_FREE_MODEL_ALLOWLIST", model)


def test_free_only_groq_requires_exact_provider_endpoint_key_and_allowlisted_model(monkeypatch):
    _enable_groq_free_only(monkeypatch)
    status = model_adapter.get_model_status()
    assert status["enabled"] is True
    assert status["configured"] is True
    assert status["free_only"] is True
    assert status["reason"] == "ready_free_only"

    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://api.groq.com.evil.example/openai/v1")
    assert model_adapter.get_model_status()["enabled"] is False
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "unlisted-model")
    assert model_adapter.get_model_status()["reason"] == "free_only_configuration_rejected"


def test_free_only_rejects_missing_key_and_non_groq_provider(monkeypatch):
    _enable_groq_free_only(monkeypatch)
    monkeypatch.delenv("AI_OS_MODEL_API_KEY")
    assert model_adapter.get_model_status()["enabled"] is False
    _enable_groq_free_only(monkeypatch)
    monkeypatch.setenv("AI_OS_MODEL_PROVIDER", "other-provider")
    assert model_adapter.get_model_status()["enabled"] is False


def test_free_only_blocks_command_backend(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_FREE_ONLY", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "command")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND", "agy")
    monkeypatch.setenv("AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED", "true")
    monkeypatch.setattr(model_adapter.shutil, "which", lambda value: "/usr/bin/agy")
    assert model_adapter.get_model_status()["enabled"] is False


def test_free_only_groq_sends_one_request_and_never_logs_secret(monkeypatch):
    _enable_groq_free_only(monkeypatch)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": json.dumps({
                    "status": "completed", "summary": "Free-tier response"
                })}}]
            }).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(model_adapter.urllib.request, "urlopen", fake_urlopen)
    result, metadata = model_adapter.generate_json("system", "task")
    assert result["summary"] == "Free-tier response"
    assert metadata["provider"] == "groq"
    assert captured["request"].full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["request"].get_header("Authorization") == "Bearer test-secret"
    assert captured["request"].get_method() == "POST"


def test_free_only_quota_error_is_not_retried_or_fallen_back(monkeypatch):
    import urllib.error

    _enable_groq_free_only(monkeypatch)
    calls = []

    def fail_once(request, timeout):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(
            request.full_url, 429, "rate limited", hdrs=None, fp=None
        )

    monkeypatch.setattr(model_adapter.urllib.request, "urlopen", fail_once)
    with pytest.raises(model_adapter.ModelQuotaExceeded, match="without automatic retry"):
        model_adapter.generate_json("system", "task")
    assert len(calls) == 1



def _enable_ovh_anonymous_free_only(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_FREE_ONLY", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "openai_compatible")
    monkeypatch.setenv("AI_OS_MODEL_PROVIDER", "ovhcloud-anonymous")
    monkeypatch.setenv(
        "AI_OS_MODEL_BASE_URL",
        "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
    )
    monkeypatch.setenv("AI_OS_MODEL_NAME", "gpt-oss-20b")
    monkeypatch.setenv("AI_OS_FREE_MODEL_ALLOWLIST", "gpt-oss-20b")
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)


def test_free_only_accepts_verified_anonymous_ovh_endpoint_without_key(monkeypatch):
    _enable_ovh_anonymous_free_only(monkeypatch)
    status = model_adapter.get_model_status()
    assert status["enabled"] is True
    assert status["configured"] is True
    assert status["provider"] == "ovhcloud-anonymous"
    assert status["api_key_present"] is False
    assert status["reason"] == "ready_free_only"


def test_free_only_rejects_anonymous_ovh_endpoint_with_key_or_wrong_model(monkeypatch):
    _enable_ovh_anonymous_free_only(monkeypatch)
    monkeypatch.setenv("AI_OS_MODEL_API_KEY", "unexpected-secret")
    assert model_adapter.get_model_status()["enabled"] is False

    _enable_ovh_anonymous_free_only(monkeypatch)
    monkeypatch.setenv("AI_OS_MODEL_NAME", "unlisted-model")
    assert model_adapter.get_model_status()["enabled"] is False

    _enable_ovh_anonymous_free_only(monkeypatch)
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://evil.example/v1")
    assert model_adapter.get_model_status()["enabled"] is False



def test_anonymous_public_provider_enforces_minimum_request_interval(monkeypatch):
    current = {"time": 100.0}
    sleeps = []
    monkeypatch.setattr(model_adapter, "_PUBLIC_MODEL_NEXT_ALLOWED", 0.0)
    monkeypatch.setattr(model_adapter.time, "monotonic", lambda: current["time"])

    def fake_sleep(seconds):
        sleeps.append(seconds)
        current["time"] += seconds

    monkeypatch.setattr(model_adapter.time, "sleep", fake_sleep)
    model_adapter._throttle_public_provider("ovhcloud-anonymous")
    model_adapter._throttle_public_provider("ovhcloud-anonymous")

    assert sleeps == [31.0]
    assert model_adapter._PUBLIC_MODEL_NEXT_ALLOWED == 162.0
    model_adapter._throttle_public_provider("another-provider")
    assert sleeps == [31.0]
