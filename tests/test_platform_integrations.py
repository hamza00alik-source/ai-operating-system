import pytest

from ai_os import platform_integrations as integrations


def test_wordpress_connection_uses_authenticated_read_only_profile(monkeypatch):
    monkeypatch.setattr(integrations.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    calls = []
    def fake_get(url, username, password):
        calls.append((url, username, password))
        return {"id": 7, "name": "Store Owner"}
    monkeypatch.setattr(integrations, "_get_json", fake_get)
    result = integrations.verify_connection("wordpress", "application-password", {
        "site_url": "https://store.example", "username": "owner"
    })
    assert result["connected"] is True
    assert result["account"] == "Store Owner"
    assert calls == [("https://store.example/wp-json/wp/v2/users/me?context=edit", "owner", "application-password")]


def test_woocommerce_connection_uses_read_only_products_request(monkeypatch):
    monkeypatch.setattr(integrations.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    calls = []
    def fake_get(url, username, password):
        calls.append((url, username, password))
        return []
    monkeypatch.setattr(integrations, "_get_json", fake_get)
    result = integrations.verify_connection("woocommerce", "consumer-secret", {
        "site_url": "https://shop.example", "consumer_key": "ck_readonly"
    })
    assert result["connected"] is True
    assert result["sampled_products"] == 0
    assert calls == [("https://shop.example/wp-json/wc/v3/products?per_page=1", "ck_readonly", "consumer-secret")]


@pytest.mark.parametrize("url", [
    "http://store.example",
    "https://localhost",
    "https://127.0.0.1",
    "https://store.example/private/path",
    "https://user:pass@store.example",
])
def test_rejects_unsafe_store_urls(url, monkeypatch):
    monkeypatch.setattr(integrations.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    with pytest.raises(ValueError):
        integrations._site_origin(url)


def test_unsupported_provider_has_no_fake_connected_state(monkeypatch):
    monkeypatch.setattr(integrations.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    with pytest.raises(ValueError, match="currently support"):
        integrations.verify_connection("meta", "some-secret-value", {"site_url": "https://example.com"})
