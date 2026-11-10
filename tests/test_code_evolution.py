import pytest

from ai_os import code_evolution


def test_readiness_fails_closed_without_token(monkeypatch):
    monkeypatch.setenv("AI_OS_CODE_EVOLUTION_ENABLED", "true")
    monkeypatch.delenv("AI_OS_GITHUB_TOKEN", raising=False)
    result = code_evolution.readiness()
    assert result["enabled"] is False
    assert result["token_configured"] is False
    assert any("AI_OS_GITHUB_TOKEN" in item for item in result["missing_configuration"])


def test_readiness_requires_explicit_enable_flag(monkeypatch):
    monkeypatch.delenv("AI_OS_CODE_EVOLUTION_ENABLED", raising=False)
    monkeypatch.setenv("AI_OS_GITHUB_TOKEN", "placeholder-token")
    result = code_evolution.readiness()
    assert result["enabled"] is False
    assert any("AI_OS_CODE_EVOLUTION_ENABLED" in item for item in result["missing_configuration"])


@pytest.mark.parametrize("path", [
    "src/ai_os/auth.py",
    "src/ai_os/api.py",
    "src/ai_os/credentials.py",
    "src/ai_os/db.py",
    "src/ai_os/social_oauth.py",
    "../secrets.py",
    "/etc/passwd",
    "src/ai_os/../../secrets.py",
    "tests/test_auth.py/../conftest.py",
    "pyproject.toml",
])
def test_protected_or_non_allowlisted_targets_are_rejected(path):
    with pytest.raises(ValueError):
        code_evolution.validate_target(path)


@pytest.mark.parametrize("path", [
    "src/ai_os/brain.py",
    "src/ai_os/executive_supervisor.py",
    "tests/test_code_evolution.py",
    "docs/ROADMAP.md",
])
def test_safe_targets_are_allowed(path):
    assert code_evolution.validate_target(path) == path
