import os
import pytest
from cryptography.fernet import Fernet
from ai_os import credential_vault


def test_credentials_are_encrypted_and_never_returned(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'vault.db'}")
    from ai_os.db import initialize_database
    initialize_database()
    credential_vault.initialize_vault()
    result = credential_vault.save_provider("groq", "llama-test", "secret-do-not-leak", True)
    assert result["configured"] and result["eligible"]
    assert "secret-do-not-leak" not in str(result)
    with credential_vault.connect() as db:
        stored = db.execute("SELECT encrypted_secret FROM provider_credentials WHERE provider='groq'").fetchone()[0]
    assert b"secret-do-not-leak" not in bytes(stored)
    assert credential_vault.get_provider_secret("groq") == ("llama-test", "secret-do-not-leak", True)


def test_vault_requires_encryption_key(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_OS_CREDENTIALS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'vault.db'}")
    with pytest.raises(RuntimeError, match="AI_OS_CREDENTIALS_ENCRYPTION_KEY"):
        credential_vault.save_provider("groq", "model", "secret", True)


def test_free_confirmation_is_mandatory(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'vault.db'}")
    from ai_os.db import initialize_database
    initialize_database()
    credential_vault.initialize_vault()
    with pytest.raises(ValueError, match="Confirm"):
        credential_vault.save_provider("groq", "model", "secret", False)
