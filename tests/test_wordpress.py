import json

import pytest

from ai_os.wordpress import (
    WordPressNotConfigured,
    WordPressReadOnlyClient,
)


def test_wordpress_requires_https_and_rejects_embedded_credentials():
    with pytest.raises(ValueError):
        WordPressReadOnlyClient("http://site.example", "owner", "app-pass")
    with pytest.raises(ValueError):
        WordPressReadOnlyClient("https://owner:pass@site.example", "owner", "app-pass")


def test_wordpress_not_configured_fails_without_network(monkeypatch):
    for name in (
        "AI_OS_WORDPRESS_URL",
        "AI_OS_WORDPRESS_USERNAME",
        "AI_OS_WORDPRESS_APPLICATION_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(WordPressNotConfigured):
        WordPressReadOnlyClient.from_environment()


def test_wordpress_content_is_minimized_and_get_only(monkeypatch):
    class Response:
        def __init__(self, data):
            self.data = json.dumps(data).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return self.data

    calls = []

    def fake_open(request, timeout):
        calls.append(request)
        return Response([{
            "id": 7,
            "date": "2026-11-06T10:00:00",
            "modified": "2026-11-06T11:00:00",
            "slug": "about",
            "status": "publish",
            "link": "https://site.example/about/",
            "title": {"rendered": "About"},
            "excerpt": {"rendered": "About this site"},
            "content": {"rendered": "not returned"},
            "author": 99,
        }])

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    client = WordPressReadOnlyClient(
        "https://site.example", "owner", "application-password"
    )
    pages = client.list_pages(per_page=500)

    assert pages[0]["title"] == "About"
    assert pages[0]["excerpt"] == "About this site"
    assert "content" not in pages[0]
    assert "author" not in pages[0]
    assert calls[0].get_method() == "GET"
    assert "application-password" not in calls[0].headers.get("Authorization", "")
    assert WordPressReadOnlyClient.status()["writes_enabled"] is False


def test_wordpress_rejects_unknown_resource():
    client = WordPressReadOnlyClient("https://site.example", "owner", "app-pass")
    with pytest.raises(ValueError):
        client._get("users")
