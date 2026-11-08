import pytest
from fastapi.testclient import TestClient

from ai_os import credentials
from ai_os.api import app


def test_vault_requires_encryption_key(monkeypatch):
    monkeypatch.delenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(credentials.CredentialVaultUnavailable):
        credentials.save_openrouter("or-test-secret", True)


def test_vault_encrypts_and_round_trips_secret(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    credentials.save_openrouter("or-test-secret", True)
    assert credentials.get_openrouter()["secret"] == "or-test-secret"
    assert credentials.credential_status() == {"configured": True, "model": "openrouter/free", "free_confirmed": True}


def test_vault_rejects_unconfirmed_free_route(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(ValueError):
        credentials.save_openrouter("or-test-secret", False)


def test_credential_write_requires_owner_key_even_in_development(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post("/llm/credentials/openrouter", json={"api_key": "or-test-secret", "confirm_free_only": True})
    assert response.status_code == 401
