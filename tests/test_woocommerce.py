import json

import pytest

from ai_os.woocommerce import (
    WooCommerceNotConfigured,
    WooCommerceReadOnlyClient,
    WooCommerceWriteDisabled,
)


def test_woocommerce_requires_https_and_rejects_embedded_credentials():
    with pytest.raises(ValueError):
        WooCommerceReadOnlyClient("http://shop.example/wp-json/wc/v3", "ck", "cs")
    with pytest.raises(ValueError):
        WooCommerceReadOnlyClient("https://user:pass@shop.example/wp-json/wc/v3", "ck", "cs")


def test_woocommerce_not_configured_fails_without_network(monkeypatch):
    for name in (
        "AI_OS_WOOCOMMERCE_URL",
        "AI_OS_WOOCOMMERCE_CONSUMER_KEY",
        "AI_OS_WOOCOMMERCE_CONSUMER_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(WooCommerceNotConfigured):
        WooCommerceReadOnlyClient.from_environment()


def test_woocommerce_product_and_order_results_are_minimized(monkeypatch):
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
        calls.append((request, timeout))
        if "/products?" in request.full_url:
            return Response([{
                "id": 1, "name": "Asset", "sku": "A1", "status": "publish",
                "price": "5.00", "permalink": "https://shop.example/asset",
                "stock_status": "instock", "description": "not returned",
            }])
        return Response([{
            "id": 9, "status": "processing", "date_created": "2026-11-06T10:00:00",
            "currency": "USD", "total": "5.00", "billing": {"email": "private@example.com"},
        }])

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    client = WooCommerceReadOnlyClient(
        "https://shop.example/wp-json/wc/v3", "consumer-key", "consumer-secret"
    )
    products = client.list_products(per_page=500)
    orders = client.list_order_statuses(status="processing")

    assert products[0]["name"] == "Asset"
    assert "description" not in products[0]
    assert orders[0]["status"] == "processing"
    assert "billing" not in orders[0]
    assert all(call[0].get_method() == "GET" for call in calls)
    assert "consumer-secret" not in calls[0][0].headers.get("Authorization", "")
    assert WooCommerceReadOnlyClient.status()["writes_enabled"] is False



def test_woocommerce_draft_creation_requires_flags_and_forces_draft(monkeypatch):
    client = WooCommerceReadOnlyClient(
        "https://shop.example/wp-json/wc/v3", "consumer-key", "consumer-secret"
    )
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED", "false")
    with pytest.raises(WooCommerceWriteDisabled):
        client.create_product_draft(name="Asset", description="Digital item", regular_price="5.00")

    monkeypatch.setenv("AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED", "true")
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps({
                "id": 77, "name": "Asset", "status": "draft",
                "permalink": "https://shop.example/?post=77",
            }).encode()

    def fake_open(request, timeout):
        calls.append(request)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    result = client.create_product_draft(
        name="Asset", description="Digital item", regular_price="5.00"
    )
    assert result["id"] == 77
    assert result["status"] == "draft"
    assert calls[0].get_method() == "POST"
    body = json.loads(calls[0].data.decode())
    assert body["status"] == "draft"
    assert body["regular_price"] == "5.00"


@pytest.mark.parametrize("price", ["-1.00", "NaN", "Infinity", "not-a-price"])
def test_woocommerce_draft_creation_rejects_invalid_price(monkeypatch, price):
    client = WooCommerceReadOnlyClient(
        "https://shop.example/wp-json/wc/v3", "consumer-key", "consumer-secret"
    )
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED", "true")
    with pytest.raises(ValueError):
        client.create_product_draft(name="Asset", description="", regular_price=price)
