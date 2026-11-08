import pytest
from cryptography.fernet import Fernet

from ai_os.credential_vault import (
    CredentialVaultError,
    initialize_credential_vault,
    list_credentials,
    resolve_credential,
    revoke_credential,
    store_credential,
)


def test_credentials_are_encrypted_and_never_returned(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'vault.db'}")
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    initialize_credential_vault()
    result = store_credential(
        provider_id="example-service",
        label="Test account",
        secret_type="api_key",
        secret={"api_key": "top-secret-value"},
    )
    assert "top-secret-value" not in str(result)
    assert "top-secret-value" not in str(list_credentials())
    assert resolve_credential(result["credential_ref"]) == {"api_key": "top-secret-value"}
    revoked = revoke_credential(result["credential_ref"])
    assert revoked["status"] == "revoked"
    with pytest.raises(CredentialVaultError, match="missing or revoked"):
        resolve_credential(result["credential_ref"])


def test_vault_fails_closed_without_key(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'vault.db'}")
    monkeypatch.delenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    initialize_credential_vault()
    with pytest.raises(CredentialVaultError, match="vault is locked"):
        store_credential(
            provider_id="example-service",
            label="Test account",
            secret_type="api_key",
            secret={"api_key": "not-stored"},
        )
