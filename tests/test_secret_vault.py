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


def test_provider_secret_vault_encrypts_github_token_with_provider_scoped_payload(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "encryption-key-for-tests-at-least-32")
    db = _database()
    vault = ProviderSecretVault(db, __import__("threading").RLock())
    token = "github-private-token-never-store-plaintext"
    assert vault.put("github_evolution", {"token": token}) == 1
    raw = db.execute("SELECT nonce,ciphertext FROM provider_secrets WHERE provider='github_evolution'").fetchone()
    assert token.encode() not in bytes(raw["ciphertext"])
    assert vault.get("github_evolution") == {"token": token}
    assert vault.status("github_evolution")["configured"] is True
    assert vault.delete("github_evolution") is True
    assert vault.get("github_evolution") is None



def test_provider_secret_vault_requires_dedicated_encryption_key(monkeypatch):
    monkeypatch.delenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-that-is-long-enough-but-not-an-encryption-key")
    vault = ProviderSecretVault(_database(), __import__("threading").RLock())
    with pytest.raises(SecretVaultError, match="OPENCOMPANY_SECRET_ENCRYPTION_KEY"):
        vault.put("unorouter", {"api_key": "private-token", "model": "model:free"})


def test_woocommerce_credentials_are_encrypted_and_isolated_per_business(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "encryption-key-for-tests-at-least-32")
    db = _database()
    vault = ProviderSecretVault(db, __import__("threading").RLock())
    agency = {
        "store_url": "https://agency.example.com",
        "consumer_key": "ck_agencyprivate123",
        "consumer_secret": "cs_agencyprivate123",
    }
    brand = {
        "store_url": "https://brand.example.com",
        "consumer_key": "ck_brandprivate123",
        "consumer_secret": "cs_brandprivate123",
    }
    assert vault.put("woocommerce:physical-agency", agency) == 1
    assert vault.put("woocommerce:physical-brand", brand) == 1
    rows = db.execute("SELECT provider,nonce,ciphertext FROM provider_secrets ORDER BY provider").fetchall()
    assert len(rows) == 2
    assert b"agencyprivate" not in bytes(rows[0]["ciphertext"])
    assert b"brandprivate" not in bytes(rows[1]["ciphertext"])
    assert vault.get("woocommerce:physical-agency") == agency
    assert vault.get("woocommerce:physical-brand") == brand
    assert vault.delete("woocommerce:physical-agency") is True
    assert vault.get("woocommerce:physical-agency") is None
    assert vault.get("woocommerce:physical-brand") == brand


def test_woocommerce_vault_rejects_unknown_business_or_extra_secret_fields(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "encryption-key-for-tests-at-least-32")
    vault = ProviderSecretVault(_database(), __import__("threading").RLock())
    payload = {
        "store_url": "https://shop.example.com",
        "consumer_key": "ck_testprivate123",
        "consumer_secret": "cs_testprivate123",
    }
    with pytest.raises(ValueError, match="unsupported provider"):
        vault.put("woocommerce:core", payload)
    with pytest.raises(ValueError, match="unsupported fields"):
        vault.put("woocommerce:physical-brand", {**payload, "unexpected": "value"})
