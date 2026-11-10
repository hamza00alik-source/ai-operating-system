import json
import hashlib
import hmac
from ai_os import marketplace_integrations as integrations


class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return json.dumps({"code": 10000, "data": {"items": [{"offerId": 1}]}}).encode()


def test_playerauctions_connection_is_hmac_signed_read_only(monkeypatch):
    captured = {}
    class FakeOpener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()
    monkeypatch.setattr(integrations.time, "time", lambda: 1000)
    monkeypatch.setattr(integrations.urllib.request, "build_opener", lambda *handlers: FakeOpener())
    result = integrations.verify_playerauctions("very-secret-key", {"api_key": "seller-api-key"})
    request = captured["request"]
    expected = hmac.new(b"very-secret-key", b"seller-api-key1000", hashlib.sha256).hexdigest()
    assert request.get_method() == "GET"
    assert request.full_url == "https://seller-api.playerauctions.com/api/v1/offers?pageIndex=1&pageSize=1"
    assert request.get_header("X-pa-api-key") == "seller-api-key"
    assert request.get_header("X-pa-timestamp") == "1000"
    assert request.get_header("X-pa-sign") == expected
    assert result["connected"] is True
    assert result["sampled_offers"] == 1
    assert "GET only" in result["external_actions"]


def test_playerauctions_rejects_failed_api_response(monkeypatch):
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size): return json.dumps({"code": 10002, "message": "Invalid signature"}).encode()
    class FakeOpener:
        def open(self, request, timeout): return FakeResponse()
    monkeypatch.setattr(integrations.urllib.request, "build_opener", lambda *handlers: FakeOpener())
    import pytest
    with pytest.raises(integrations.MarketplaceCheckError, match="Invalid signature"):
        integrations.verify_playerauctions("very-secret-key", {"api_key": "seller-api-key"})
