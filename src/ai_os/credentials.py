"""Encrypted owner-managed provider credentials."""
from __future__ import annotations

import os
import sqlite3
from cryptography.fernet import Fernet, InvalidToken
from ai_os.db import connect


class CredentialVaultUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = (os.getenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY") or os.getenv("AI_OS_CREDENTIALS_ENCRYPTION_KEY") or "").strip()
    if not key:
        raise CredentialVaultUnavailable(
            "Credential vault is locked. Configure AI_OS_CREDENTIAL_ENCRYPTION_KEY (or AI_OS_CREDENTIALS_ENCRYPTION_KEY) on the hosting server."
        )
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise CredentialVaultUnavailable("Credential encryption key is invalid.") from exc


def save_openrouter(api_key: str, free_confirmed: bool) -> None:
    if not api_key or len(api_key) > 512:
        raise ValueError("Enter a valid OpenRouter API key.")
    if not free_confirmed:
        raise ValueError("Confirm that the selected route is restricted to free models.")
    encrypted = _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")
    with connect() as db:
        db.execute(
            """INSERT INTO provider_credentials(provider, encrypted_secret, model, base_url, free_confirmed)
               VALUES('openrouter', ?, 'openrouter/free', 'https://openrouter.ai/api/v1', 1)
               ON CONFLICT(provider) DO UPDATE SET encrypted_secret=excluded.encrypted_secret,
               model=excluded.model, base_url=excluded.base_url,
               free_confirmed=excluded.free_confirmed""",
            (encrypted,),
        )


PROVIDER_ENDPOINTS = {
    "gemini": "https://generativelanguage.googleapis.com",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "unorouter": "https://api.unorouter.com/v1",
}


def save_provider_credential(provider: str, api_key: str, model: str, free_confirmed: bool) -> None:
    if provider not in PROVIDER_ENDPOINTS:
        raise ValueError("This provider cannot be configured through the credential vault.")
    if not api_key or len(api_key) > 512:
        raise ValueError("Enter a valid provider API key.")
    if not model or len(model) > 200:
        raise ValueError("Enter a valid model identifier.")
    if provider == "unorouter" and not model.endswith(":free"):
        raise ValueError("UnoRouter personal testing is restricted to model IDs ending in :free.")
    if not free_confirmed:
        raise ValueError("Confirm that this provider account and model are currently free.")
    encrypted = _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")
    with connect() as db:
        db.execute(
            """INSERT INTO provider_credentials(provider, encrypted_secret, model, base_url, free_confirmed)
               VALUES(?, ?, ?, ?, 1)
               ON CONFLICT(provider) DO UPDATE SET encrypted_secret=excluded.encrypted_secret,
               model=excluded.model, base_url=excluded.base_url, free_confirmed=excluded.free_confirmed""",
            (provider, encrypted, model, PROVIDER_ENDPOINTS[provider]),
        )


def get_provider_credential(provider: str) -> dict | None:
    try:
        with connect() as db:
            row = db.execute(
                "SELECT encrypted_secret, model, base_url, free_confirmed FROM provider_credentials WHERE provider=?",
                (provider,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    try:
        secret = _fernet().decrypt(row["encrypted_secret"].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError) as exc:
        raise CredentialVaultUnavailable("Stored provider credential could not be decrypted.") from exc
    return {
        "secret": secret, "model": row["model"], "base_url": row["base_url"],
        "free_confirmed": bool(row["free_confirmed"]),
    }


def provider_credential_statuses() -> dict:
    statuses = {}
    try:
        with connect() as db:
            rows = db.execute("SELECT provider, model, free_confirmed FROM provider_credentials").fetchall()
    except sqlite3.OperationalError:
        rows = []
    for row in rows:
        statuses[row["provider"]] = {
            "configured": True, "model": row["model"],
            "free_confirmed": bool(row["free_confirmed"]),
        }
    return statuses


def get_openrouter() -> dict | None:
    try:
        with connect() as db:
            row = db.execute(
                "SELECT encrypted_secret, model, base_url, free_confirmed FROM provider_credentials WHERE provider='openrouter'"
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    try:
        secret = _fernet().decrypt(row["encrypted_secret"].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError) as exc:
        raise CredentialVaultUnavailable("Stored provider credential could not be decrypted.") from exc
    return {
        "secret": secret, "model": row["model"], "base_url": row["base_url"],
        "free_confirmed": bool(row["free_confirmed"]),
    }


def credential_status() -> dict:
    try:
        with connect() as db:
            row = db.execute(
                "SELECT model, free_confirmed FROM provider_credentials WHERE provider='openrouter'"
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    return {
        "configured": row is not None,
        "model": row["model"] if row else None,
        "free_confirmed": bool(row["free_confirmed"]) if row else False,
    }
