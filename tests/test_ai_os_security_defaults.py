"""Regression tests for fail-closed legacy AIOS deployment defaults."""
import pytest
from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.config import get_settings


def test_unspecified_environment_defaults_to_production(monkeypatch):
    monkeypatch.delenv("AI_OS_ENV", raising=False)
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)

    settings = get_settings()

    assert settings.environment == "production"
    assert settings.api_key == ""


def test_application_refuses_to_start_without_key_when_environment_is_unspecified(monkeypatch):
    monkeypatch.delenv("AI_OS_ENV", raising=False)
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="AI_OS_API_KEY"):
        with TestClient(app):
            pass


def test_development_auth_bypass_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)

    assert get_settings().environment == "development"
