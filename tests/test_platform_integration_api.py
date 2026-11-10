import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from ai_os import platform_integrations
from ai_os.api import app
from ai_os.db import initialize_database


@pytest.fixture
def owner_client(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "owner-connection-test-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "connections.db"))
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(platform_integrations.socket, "getaddrinfo", lambda *a, **k: [
        (None, None, None, None, ("93.184.216.34", 443))
    ])
    initialize_database()
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/auth/session", json={"api_key": "owner-connection-test-key"})
        assert login.status_code == 200
        yield client


def test_owner_can_connect_and_retest_wordpress_without_exposing_secret(owner_client, monkeypatch):
    monkeypatch.setattr(platform_integrations, "_get_json", lambda *a, **k: {"id": 5, "name": "Owner"})
    response = owner_client.post("/business-integrations/physical-brand/wordpress/connect", json={
        "secret": "application-password-secret",
        "config": {"site_url": "https://store.example", "username": "owner"}
    })
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["verification"]["connected"] is True
    assert "application-password-secret" not in response.text

    tested = owner_client.post("/business-integrations/physical-brand/wordpress/test")
    assert tested.status_code == 200
    assert tested.json()["connected"] is True


def test_failed_platform_verification_does_not_save_credentials(owner_client, monkeypatch):
    def fail(*a, **k):
        raise platform_integrations.IntegrationCheckError("invalid credentials")
    monkeypatch.setattr(platform_integrations, "_get_json", fail)
    response = owner_client.post("/business-integrations/physical-agency/woocommerce/connect", json={
        "secret": "consumer-secret",
        "config": {"site_url": "https://shop.example", "consumer_key": "consumer-key"}
    })
    assert response.status_code == 502
    listing = owner_client.get("/business-integrations/physical-agency")
    assert listing.status_code == 200
    assert listing.json()["integrations"] == []


def test_owner_cannot_claim_unsupported_social_login_is_connected(owner_client):
    response = owner_client.post("/business-integrations/digital-products/meta/connect", json={
        "secret": "placeholder-secret",
        "config": {"site_url": "https://example.com"}
    })
    assert response.status_code == 422
