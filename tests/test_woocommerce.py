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
            "currency": "USD", "total": "5.00", "date_paid": "2026-11-06T10:01:00",
            "billing": {"email": "private@example.com"},
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
    assert orders[0]["payment_status"] == "paid"
    assert orders[0]["date_paid"] == "2026-11-06T10:01:00"
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


@pytest.mark.parametrize("price", ["-1.00", "NaN", "Infinity", "not-a-price", "1e100"])
def test_woocommerce_draft_creation_rejects_invalid_price(monkeypatch, price):
    client = WooCommerceReadOnlyClient(
        "https://shop.example/wp-json/wc/v3", "consumer-key", "consumer-secret"
    )
    monkeypatch.setenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED", "true")
    with pytest.raises(ValueError):
        client.create_product_draft(name="Asset", description="", regular_price=price)



def test_woocommerce_payment_status_is_not_confirmed_without_date_paid(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps([{
                "id": 10, "status": "pending", "date_created": "2026-11-07T00:00:00",
                "date_paid": None, "currency": "USD", "total": "9.00",
                "billing": {"email": "private@example.com"},
            }]).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
    client = WooCommerceReadOnlyClient(
        "https://shop.example/wp-json/wc/v3", "consumer-key", "consumer-secret"
    )
    order = client.list_order_statuses()[0]
    assert order["payment_status"] == "not_confirmed"
    assert order["date_paid"] is None
    assert "billing" not in order



def test_woocommerce_client_resolves_one_encrypted_vault_credential(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient
    from ai_os.api import app
    from ai_os.credential_vault import store_credential

    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'woocommerce-vault.db'}")
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    for name in (
        "AI_OS_WOOCOMMERCE_URL",
        "AI_OS_WOOCOMMERCE_CONSUMER_KEY",
        "AI_OS_WOOCOMMERCE_CONSUMER_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    with TestClient(app):
        store_credential(
            provider_id="woocommerce",
            label="Primary store",
            secret_type="api_credentials",
            secret={
                "url": "https://shop.example/wp-json/wc/v3",
                "consumer_key": "ck_test",
                "consumer_secret": "cs_test",
            },
        )
        client = WooCommerceReadOnlyClient.from_environment()
        status = WooCommerceReadOnlyClient.status()

    assert client.base_url == "https://shop.example/wp-json/wc/v3/"
    assert status["configured"] is True
    assert status["credential_source"] == "vault"
    assert status["credential_verified"] is False
    assert status["writes_enabled"] is False


def test_woocommerce_vault_resolution_fails_closed_when_multiple_stores_exist(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient
    from ai_os.api import app
    from ai_os.credential_vault import store_credential

    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'woocommerce-ambiguous.db'}")
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    for name in (
        "AI_OS_WOOCOMMERCE_URL",
        "AI_OS_WOOCOMMERCE_CONSUMER_KEY",
        "AI_OS_WOOCOMMERCE_CONSUMER_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    with TestClient(app):
        for label, host in (
            ("Primary store", "https://one.example"),
            ("Secondary store", "https://two.example"),
        ):
            store_credential(
                provider_id="woocommerce",
                label=label,
                secret_type="api_credentials",
                secret={
                    "url": host + "/wp-json/wc/v3",
                    "consumer_key": "ck_test",
                    "consumer_secret": "cs_test",
                },
            )
        with pytest.raises(WooCommerceNotConfigured):
            WooCommerceReadOnlyClient.from_environment()
        status = WooCommerceReadOnlyClient.status()

    assert status["configured"] is False
    assert status["credential_source"] == "ambiguous_vault_entries"
