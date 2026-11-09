import json
from urllib.error import URLError

import pytest

from ai_os import website_api


def test_unconfigured_status_is_safe(monkeypatch):
    monkeypatch.delenv("AI_OS_API_ANYTHING_URL", raising=False)
    monkeypatch.delenv("AI_OS_API_ANYTHING_TOKEN", raising=False)
    result = website_api.status()
    assert result["configured"] is False
    assert result["connected"] is False
    assert "secret-token" not in json.dumps(result)


def test_call_read_forces_tier_one_and_never_write(monkeypatch):
    monkeypatch.setenv("AI_OS_API_ANYTHING_URL", "https://api-anything.internal")
    monkeypatch.setenv("AI_OS_API_ANYTHING_TOKEN", "secret-token")
    captured = {}

    def fake_request(method, path, body=None, **kwargs):
        captured.update(method=method, path=path, body=body, kwargs=kwargs)
        return {"ok": True, "data": [{"title": "test"}]}

    monkeypatch.setattr(website_api, "_request", fake_request)
    result = website_api.call_read("hacker-news", "search", {"query": "sqlite"})
    assert result["ok"] is True
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/call/hacker-news/search"
    assert captured["body"]["maxTier"] == 1
    assert "/write/" not in captured["path"]


def test_call_read_rejects_invalid_operation_names(monkeypatch):
    with pytest.raises(ValueError):
        website_api.call_read("../evil", "search", {})


def test_configuration_rejects_embedded_credentials(monkeypatch):
    monkeypatch.setenv("AI_OS_API_ANYTHING_URL", "https://user:pass@example.com")
    monkeypatch.setenv("AI_OS_API_ANYTHING_TOKEN", "secret-token")
    with pytest.raises(website_api.WebsiteApiUnavailable):
        website_api._configuration()


def test_redirect_must_remain_same_origin():
    import urllib.request
    handler = website_api._SameOriginRedirect()
    request = urllib.request.Request("https://api.example/v1/health")
    with pytest.raises(website_api.WebsiteApiUnavailable):
        handler.redirect_request(request, None, 302, "Found", {}, "https://attacker.example/steal")
