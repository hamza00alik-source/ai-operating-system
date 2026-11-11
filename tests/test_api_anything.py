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
    client = ApiAnythingClient("https://api-anything.internal:8787", "secret-token", transport=transport)
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



def test_api_anything_batch_rejects_oversized_and_non_json_arguments():
    client = ApiAnythingClient("https://api.example", "secret", transport=lambda *a, **k: Response({}))
    with pytest.raises(ValueError, match="8000 characters"):
        client.call_batch([{"site": "github", "op": "search", "args": {"q": "x" * 9000}}])
    with pytest.raises(ValueError, match="JSON-serializable"):
        client.call_batch([{"site": "github", "op": "search", "args": {"q": object()}}])


def test_api_anything_rejects_cleartext_external_urls_and_accepts_private_network_http():
    with pytest.raises(ValueError, match="must use HTTPS"):
        ApiAnythingClient("http://api.example.com", "secret-token")
    with pytest.raises(ValueError, match="must use HTTPS"):
        ApiAnythingClient("http://10.0.0.4:8787", "secret-token")
    ApiAnythingClient("http://127.0.0.1:8787", "secret-token")
    ApiAnythingClient("http://api-anything.railway.internal:8787", "secret-token")


def test_api_anything_rejects_url_embedded_credentials_and_query_strings():
    with pytest.raises(ValueError):
        ApiAnythingClient("https://user:password@api.example.com", "secret-token")
    with pytest.raises(ValueError):
        ApiAnythingClient("https://api.example.com?token=leak", "secret-token")
