import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from ai_os import marketplace_integrations
from ai_os.api import app
from ai_os.db import initialize_database


@pytest.fixture
def owner_marketplace_client(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "owner-marketplace-test-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "marketplace.db"))
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    initialize_database()
    with TestClient(app, base_url="https://testserver") as client:
        client.headers.update({"X-API-Key": "owner-marketplace-test-key"})
        yield client


def test_playerauctions_credentials_saved_only_after_readonly_verification(owner_marketplace_client, monkeypatch):
    monkeypatch.setattr(marketplace_integrations, "verify_playerauctions", lambda secret, config: {
        "provider": "playerauctions", "connected": True, "capability": "read-only seller offer access",
        "sampled_offers": 0, "external_actions": "GET only"
    })
    response = owner_marketplace_client.post(
        "/business-integrations/digital-products/playerauctions/connect",
        json={"secret": "player-auctions-secret", "config": {"api_key": "player-auctions-key"}})
    assert response.status_code == 200
    assert response.json()["verification"]["connected"] is True
    assert "player-auctions-secret" not in response.text


def test_failed_playerauctions_verification_does_not_store_credentials(owner_marketplace_client, monkeypatch):
    def fail(*args, **kwargs):
        raise marketplace_integrations.MarketplaceCheckError("Invalid signature")
    monkeypatch.setattr(marketplace_integrations, "verify_playerauctions", fail)
    response = owner_marketplace_client.post(
        "/business-integrations/physical-agency/playerauctions/connect",
        json={"secret": "player-auctions-secret", "config": {"api_key": "player-auctions-key"}})
    assert response.status_code == 502
    listing = owner_marketplace_client.get("/business-integrations/physical-agency")
    assert listing.status_code == 200
    assert listing.json()["integrations"] == []
