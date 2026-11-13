import json

import pytest

from opencompany_core.woocommerce_readonly import (
    WooCommerceReadError, WooCommerceReadOnlyClient,
)


class _Response:
    def __init__(self, value):
        self._raw = json.dumps(value).encode()

    def read(self, limit):
        return self._raw[:limit]


def _client(rows, captured):
    def transport(request, timeout):
        captured.append((request, timeout))
        return _Response(rows)
    return WooCommerceReadOnlyClient(
        "https://shop.example.com", "ck_testkey123", "cs_testsecret123",
        transport=transport,
    )


def test_products_uses_only_get_and_returns_minimized_fields():
    captured = []
    client = _client([{
        "id": 7, "name": "Sample", "sku": "SKU-7", "status": "publish",
        "price": "12.00", "stock_status": "instock",
        "description": "long description", "meta_data": [{"secret": "omit"}],
    }], captured)
    result = client.products(page=1, per_page=10)
    request, timeout = captured[0]
    assert request.get_method() == "GET"
    assert request.full_url.endswith("/wp-json/wc/v3/products?page=1&per_page=10")
    assert timeout == 10
    assert result["products"] == [{
        "id": 7, "name": "Sample", "type": None, "status": "publish",
        "sku": "SKU-7", "price": "12.00", "stock_status": "instock",
        "manage_stock": None, "stock_quantity": None, "date_modified": None,
    }]
    assert "description" not in str(result)
    assert "meta_data" not in str(result)


def test_orders_omit_customer_personal_data():
    captured = []
    client = _client([{
        "id": 12, "status": "processing", "currency": "USD",
        "total": "30.00", "date_created": "2026-01-01T00:00:00",
        "billing": {"email": "private@example.com", "first_name": "Private"},
        "line_items": [{"name": "Item", "quantity": 2}],
    }], captured)
    result = client.orders()
    assert result["orders"][0]["id"] == 12
    assert result["orders"][0]["line_items"] == [{"name": "Item", "quantity": 2}]
    assert "private@example.com" not in str(result)
    assert "Private" not in str(result)


@pytest.mark.parametrize("url", [
    "http://shop.example.com", "https://user:pass@shop.example.com",
    "https://127.0.0.1", "https://localhost", "https://shop.local",
    "https://shop.example.com:8443", "https://shop.example.com/?token=x",
])
def test_rejects_unsafe_store_urls(url):
    with pytest.raises(ValueError):
        WooCommerceReadOnlyClient(url, "ck_testkey123", "cs_testsecret123")


@pytest.mark.parametrize("page,per_page", [(0, 10), (6, 10), (1, 51)])
def test_bounds_pagination(page, per_page):
    client = WooCommerceReadOnlyClient(
        "https://shop.example.com", "ck_testkey123", "cs_testsecret123",
        transport=lambda request, timeout: _Response([]),
    )
    with pytest.raises(ValueError):
        client.products(page=page, per_page=per_page)


def test_rejects_unexpected_response_shape():
    client = WooCommerceReadOnlyClient(
        "https://shop.example.com", "ck_testkey123", "cs_testsecret123",
        transport=lambda request, timeout: _Response({"products": []}),
    )
    with pytest.raises(WooCommerceReadError, match="unexpected response shape"):
        client.products()


def test_rejects_response_over_limit():
    class LargeResponse:
        def read(self, limit):
            return b"x" * limit
    client = WooCommerceReadOnlyClient(
        "https://shop.example.com", "ck_testkey123", "cs_testsecret123",
        transport=lambda request, timeout: LargeResponse(),
    )
    with pytest.raises(WooCommerceReadError, match="size limit"):
        client.products()
