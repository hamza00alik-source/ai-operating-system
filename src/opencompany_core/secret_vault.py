"""Authenticated encryption for owner-managed provider credentials.

Secrets are encrypted with AES-256-GCM before SQLite persistence. The
encryption key is derived from OPENCOMPANY_SECRET_ENCRYPTION_KEY when present,
otherwise from the high-entropy owner API key. Rotating the fallback owner key
requires re-entering provider credentials.
"""
from __future__ import annotations
import json, os, secrets, sqlite3
from datetime import datetime, timezone
from threading import RLock
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

class SecretVaultError(RuntimeError):
    pass

class ProviderSecretVault:
    """SQLite-backed encrypted secret storage; plaintext stays in process memory."""
    _SALT = b"opencompany-provider-secret-vault-v1"
    _INFO = b"opencompany/aes-256-gcm/provider-secrets"

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db, self._lock = connection, lock
        with self._lock:
            self._db.execute("""CREATE TABLE IF NOT EXISTS provider_secrets (
                provider TEXT PRIMARY KEY, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL,
                updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)""")

    @staticmethod
    def _key_material() -> bytes:
        value = os.environ.get("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "").strip()
        if not value:
            value = os.environ.get("OPENCOMPANY_OWNER_API_KEY", "").strip()
        if len(value) < 32:
            raise SecretVaultError("Set a 32-character encryption key or a high-entropy owner API key before saving provider credentials.")
        return value.encode()

    @classmethod
    def _cipher(cls) -> AESGCM:
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=cls._SALT, info=cls._INFO).derive(cls._key_material())
        return AESGCM(key)

    def put(self, provider: str, value: dict[str, str]) -> int:
        if provider not in {"unorouter", "github_evolution"}:
            raise ValueError("unsupported provider secret")
        required = ("api_key", "model") if provider == "unorouter" else ("token",)
        if any(not isinstance(value.get(key), str) or not value[key].strip() for key in required):
            raise ValueError("provider secret payload is incomplete")
        nonce = secrets.token_bytes(12)
        aad = f"opencompany:provider:{provider}:v1".encode()
        plaintext = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ciphertext = self._cipher().encrypt(nonce, plaintext, aad)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            row = self._db.execute("SELECT revision FROM provider_secrets WHERE provider=?", (provider,)).fetchone()
            revision = int(row["revision"]) + 1 if row else 1
            self._db.execute("""INSERT INTO provider_secrets(provider,nonce,ciphertext,updated_at,revision)
                VALUES(?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET nonce=excluded.nonce,
                ciphertext=excluded.ciphertext,updated_at=excluded.updated_at,revision=excluded.revision""",
                (provider, nonce, ciphertext, now, revision))
        return revision

    def get(self, provider: str) -> dict[str, str] | None:
        if provider not in {"unorouter", "github_evolution"}:
            raise ValueError("unsupported provider secret")
        with self._lock:
            row = self._db.execute("SELECT nonce,ciphertext FROM provider_secrets WHERE provider=?", (provider,)).fetchone()
        if row is None:
            return None
        aad = f"opencompany:provider:{provider}:v1".encode()
        try:
            raw = self._cipher().decrypt(bytes(row["nonce"]), bytes(row["ciphertext"]), aad)
            value = json.loads(raw.decode())
            if not isinstance(value, dict):
                raise ValueError("invalid secret payload")
            if provider == "unorouter":
                if not isinstance(value.get("api_key"), str) or not isinstance(value.get("model"), str):
                    raise ValueError("invalid UnoRouter secret payload")
                return {"api_key": value["api_key"], "model": value["model"]}
            if not isinstance(value.get("token"), str):
                raise ValueError("invalid GitHub secret payload")
            return {"token": value["token"]}
        except Exception as exc:
            raise SecretVaultError("Stored provider credentials could not be decrypted; verify the server encryption key.") from exc

    def delete(self, provider: str) -> bool:
        if provider not in {"unorouter", "github_evolution"}:
            raise ValueError("unsupported provider secret")
        with self._lock:
            cursor = self._db.execute("DELETE FROM provider_secrets WHERE provider=?", (provider,))
        return cursor.rowcount == 1

    def status(self, provider: str) -> dict[str, object]:
        with self._lock:
            row = self._db.execute("SELECT updated_at,revision FROM provider_secrets WHERE provider=?", (provider,)).fetchone()
        return {"configured": row is not None, "updated_at": row["updated_at"] if row else None,
                "revision": int(row["revision"]) if row else 0}
