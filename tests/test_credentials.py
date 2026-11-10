import pytest
from fastapi.testclient import TestClient

from ai_os import credentials
from ai_os.api import app
from ai_os.db import connect, initialize_database


@pytest.fixture(autouse=True)
def isolated_credential_database(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "credentials-test.db"))
    initialize_database()


def test_vault_requires_encryption_key(monkeypatch):
    monkeypatch.delenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(credentials.CredentialVaultUnavailable):
        credentials.save_openrouter("or-test-secret", True)


def test_vault_encrypts_and_round_trips_secret(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    credentials.save_openrouter("or-test-secret", True)
    with connect() as db:
        encrypted = db.execute("SELECT encrypted_secret FROM provider_credentials WHERE provider='openrouter'").fetchone()[0]
    assert "or-test-secret" not in encrypted
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



def test_unorouter_personal_credential_is_encrypted_and_requires_free_model(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    credentials.save_provider_credential("unorouter", "uno-test-secret", "sample-model:free", True)
    with connect() as db:
        encrypted = db.execute("SELECT encrypted_secret FROM provider_credentials WHERE provider='unorouter'").fetchone()[0]
    assert "uno-test-secret" not in encrypted
    saved = credentials.get_provider_credential("unorouter")
    assert saved["secret"] == "uno-test-secret"
    assert saved["model"] == "sample-model:free"
    with pytest.raises(ValueError):
        credentials.save_provider_credential("unorouter", "uno-test-secret", "sample-model", True)
    credentials.save_provider_credential("unorouter", "uno-test-secret", "paid-model", False)
    assert credentials.get_provider_credential("unorouter")["model"] == "paid-model"
    assert credentials.get_provider_credential("unorouter")["free_confirmed"] is False



def test_cloudflare_credential_requires_account_specific_https_endpoint(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(ValueError, match="Cloudflare URL"):
        credentials.save_provider_credential(
            "cloudflare", "cloudflare-test-token", "@cf/meta/llama", True,
            "http://api.cloudflare.com/client/v4/accounts/12345678901234567890123456789012/ai/run",
        )
    with pytest.raises(ValueError, match="Cloudflare URL"):
        credentials.save_provider_credential(
            "cloudflare", "cloudflare-test-token", "@cf/meta/llama", True,
            "https://evil.example/client/v4/accounts/12345678901234567890123456789012/ai/run",
        )


def test_cloudflare_credential_is_encrypted_and_stores_validated_account_endpoint(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    endpoint = "https://api.cloudflare.com/client/v4/accounts/12345678901234567890123456789012/ai/run"
    credentials.save_provider_credential(
        "cloudflare", "cloudflare-test-token", "@cf/meta/llama", True, endpoint
    )
    saved = credentials.get_provider_credential("cloudflare")
    assert saved["secret"] == "cloudflare-test-token"
    assert saved["base_url"] == endpoint
    assert saved["free_confirmed"] is True
