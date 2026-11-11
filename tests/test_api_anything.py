import json
from urllib.parse import urlparse

import pytest

from opencompany_core.api_anything import ApiAnythingClient


class Response:
    def __init__(self, value):
        self.value = value
    def read(self, limit):
        return json.dumps(self.value).encode()


def test_api_anything_read_calls_are_forced_to_tier_one_and_use_bearer_token():
    seen = {}
    def transport(request, timeout=60):
        seen["method"] = request.method
        seen["path"] = urlparse(request.full_url).path
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data.decode())
        return Response({"ok": True, "class": "ok", "data": [{"title": "SQLite"}]})
    client = ApiAnythingClient("http://api-anything.internal:8787", "secret-token", transport=transport)
    result = client.call_read("hacker-news", "search", {"query": "sqlite"})
    assert result["ok"] is True
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/call/hacker-news/search"
    assert seen["auth"] == "Bearer secret-token"
    assert seen["body"]["maxTier"] == 1
    assert seen["body"]["args"] == {"query": "sqlite"}
    assert not hasattr(client, "call_write")


def test_api_anything_batch_caps_concurrency_and_tier():
    seen = {}
    def transport(request, timeout=60):
        seen["body"] = json.loads(request.data.decode())
        return Response({"ok": True, "results": []})
    client = ApiAnythingClient("https://api.example", "secret", transport=transport)
    client.call_batch([
        {"site": "hacker-news", "op": "search", "args": {"query": "sqlite"}},
        {"site": "github", "op": "searchRepos", "args": {"q": "sqlite"}},
    ])
    assert seen["body"]["concurrency"] == 2
    assert seen["body"]["maxTier"] == 1


def test_api_anything_rejects_invalid_site_operation_and_large_arguments():
    client = ApiAnythingClient("https://api.example", "secret", transport=lambda *a, **k: Response({}))
    with pytest.raises(ValueError):
        client.list_operations("../secret")
    with pytest.raises(ValueError):
        client.call_read("site", "../write", {})
    with pytest.raises(ValueError):
        client.call_read("site", "search", {"query": "x" * 9000})
