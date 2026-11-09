"""Encrypted storage for owner-managed provider credentials."""
from __future__ import annotations

import os
from cryptography.fernet import Fernet, InvalidToken

from ai_os.db import connect

PROVIDER_META = {
    "gemini": {"name": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com", "protocol": "gemini"},
    "groq": {"name": "Groq", "base_url": "https://api.groq.com/openai/v1", "protocol": "openai"},
    "mistral": {"name": "Mistral", "base_url": "https://api.mistral.ai/v1", "protocol": "openai"},
}


def _fernet() -> Fernet:
    key = os.getenv("AI_OS_CREDENTIALS_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("Credential vault is not initialized: set AI_OS_CREDENTIALS_ENCRYPTION_KEY in the hosting secret manager.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise RuntimeError("Credential vault encryption key is invalid; generate a Fernet key.") from None


def initialize_vault() -> None:
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS provider_credentials (
            provider TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            encrypted_secret BLOB NOT NULL,
            free_confirmed INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )""")


def save_provider(provider: str, model: str, api_key: str, free_confirmed: bool) -> dict:
    if provider not in PROVIDER_META:
        raise ValueError("This provider is not supported by the secure vault.")
    model = model.strip()
    api_key = api_key.strip()
    if not model or len(model) > 160:
        raise ValueError("Enter a valid model identifier.")
    if not api_key or len(api_key) > 4096:
        raise ValueError("Enter a valid API key.")
    if free_confirmed is not True:
        raise ValueError("Confirm that you checked the provider's current pricing and want to enable this endpoint.")
    token = _fernet().encrypt(api_key.encode("utf-8"))
    from datetime import datetime, timezone
    with connect() as db:
        db.execute("""INSERT INTO provider_credentials(provider,model,encrypted_secret,free_confirmed,enabled,updated_at)
            VALUES(?,?,?,?,1,?) ON CONFLICT(provider) DO UPDATE SET
            model=excluded.model, encrypted_secret=excluded.encrypted_secret,
            free_confirmed=excluded.free_confirmed, enabled=1, updated_at=excluded.updated_at""",
            (provider, model, token, 1, datetime.now(timezone.utc).isoformat()))
    return provider_status(provider)


def get_provider_secret(provider: str) -> tuple[str, str, bool] | None:
    with connect() as db:
        row = db.execute("SELECT model,encrypted_secret,free_confirmed,enabled FROM provider_credentials WHERE provider=?", (provider,)).fetchone()
    if not row or not row["enabled"]:
        return None
    try:
        secret = _fernet().decrypt(bytes(row["encrypted_secret"])).decode("utf-8")
    except (InvalidToken, ValueError):
        raise RuntimeError("Stored provider credential could not be decrypted. Check the vault encryption key.") from None
    return row["model"], secret, bool(row["free_confirmed"])


def provider_status(provider: str) -> dict:
    meta = PROVIDER_META[provider]
    with connect() as db:
        row = db.execute("SELECT model,free_confirmed,enabled,updated_at FROM provider_credentials WHERE provider=?", (provider,)).fetchone()
    configured = bool(row)
    return {"id": provider, "name": meta["name"], "configured": configured,
            "enabled": bool(row["enabled"]) if row else False,
            "eligible": bool(row and row["enabled"] and row["free_confirmed"]),
            "free_confirmed": bool(row["free_confirmed"]) if row else False,
            "model": row["model"] if row else None,
            "updated_at": row["updated_at"] if row else None,
            "secret_saved": configured,
            "reason": None if configured else "No API key saved."}


def list_vault_providers() -> list[dict]:
    return [provider_status(provider) for provider in PROVIDER_META]


def delete_provider(provider: str) -> bool:
    if provider not in PROVIDER_META:
        raise ValueError("Unknown provider.")
    with connect() as db:
        cursor = db.execute("DELETE FROM provider_credentials WHERE provider=?", (provider,))
    return cursor.rowcount > 0
