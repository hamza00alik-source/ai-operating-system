import sqlite3
import pytest

from opencompany_core.secret_vault import ProviderSecretVault, SecretVaultError


def _database():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def test_provider_secret_vault_encrypts_and_persists_credentials(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "encryption-key-for-tests-at-least-32")
    db = _database()
    vault = ProviderSecretVault(db, __import__("threading").RLock())
    secret = "unorouter-private-token-never-store-plaintext"
    revision = vault.put("unorouter", {"api_key": secret, "model": "qwen/model:free"})

    raw = db.execute("SELECT nonce,ciphertext FROM provider_secrets").fetchone()
    assert secret.encode() not in bytes(raw["ciphertext"])
    assert revision == 1
    assert vault.get("unorouter") == {"api_key": secret, "model": "qwen/model:free"}
    assert vault.status("unorouter")["configured"] is True


def test_provider_secret_vault_detects_encryption_key_rotation(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "first-encryption-key-is-at-least-32")
    db = _database()
    lock = __import__("threading").RLock()
    ProviderSecretVault(db, lock).put("unorouter", {"api_key": "private-token", "model": "model:free"})
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "second-encryption-key-is-at-least-32")
    with pytest.raises(SecretVaultError, match="could not be decrypted"):
        ProviderSecretVault(db, lock).get("unorouter")


def test_provider_secret_vault_revisions_and_removes_credentials(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "encryption-key-for-tests-at-least-32")
    db = _database()
    vault = ProviderSecretVault(db, __import__("threading").RLock())
    assert vault.put("unorouter", {"api_key": "token-one", "model": "model:free"}) == 1
    assert vault.put("unorouter", {"api_key": "token-two", "model": "model-two:free"}) == 2
    assert vault.get("unorouter")["api_key"] == "token-two"
    assert vault.delete("unorouter") is True
    assert vault.get("unorouter") is None
    assert vault.delete("unorouter") is False
