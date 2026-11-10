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
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "cloudflare": "",
    "unorouter": "https://api.unorouter.com/v1",
}


def save_provider_credential(provider: str, api_key: str, model: str, free_confirmed: bool, base_url: str | None = None) -> None:
    if provider not in PROVIDER_ENDPOINTS:
        raise ValueError("This provider cannot be configured through the credential vault.")
    if not api_key or len(api_key) > 512:
        raise ValueError("Enter a valid provider API key.")
    if not model or len(model) > 200:
        raise ValueError("Enter a valid model identifier.")
    if provider == "unorouter":
        if model.endswith(":free") and not free_confirmed:
            raise ValueError("Confirm that this :free model is zero-cost before enabling automatic free-only routing.")
        if not model.endswith(":free") and free_confirmed:
            raise ValueError("A paid UnoRouter model cannot be marked free or enabled for automatic routing.")
    elif not free_confirmed:
        raise ValueError("Confirm that this provider account and model are currently free.")
    endpoint = PROVIDER_ENDPOINTS[provider]
    if provider == "cloudflare":
        import re
        from urllib.parse import urlsplit
        endpoint = (base_url or "").strip().rstrip("/")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or parsed.hostname != "api.cloudflare.com"
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.query or parsed.fragment
                or not re.fullmatch(r"/client/v4/accounts/[0-9a-fA-F]{32}/ai/run", parsed.path)):
            raise ValueError("Cloudflare URL must be the account-specific HTTPS /client/v4/accounts/{32-character-account-id}/ai/run endpoint.")
    elif base_url:
        raise ValueError("A custom base URL is accepted only for Cloudflare Workers AI.")
    encrypted = _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")
    with connect() as db:
        db.execute(
            """INSERT INTO provider_credentials(provider, encrypted_secret, model, base_url, free_confirmed)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET encrypted_secret=excluded.encrypted_secret,
               model=excluded.model, base_url=excluded.base_url, free_confirmed=excluded.free_confirmed""",
            (provider, encrypted, model, endpoint, int(free_confirmed)),
        )



def update_provider_model(provider: str, model: str, free_confirmed: bool) -> None:
    """Change the selected model without resubmitting or exposing the stored API key."""
    if provider not in PROVIDER_ENDPOINTS:
        raise ValueError("This provider cannot be configured through the credential vault.")
    if not model or len(model) > 200 or model == "__catalog_only__":
        raise ValueError("Choose an exact model ID returned by the provider.")
    if provider == "unorouter":
        if model.endswith(":free") and not free_confirmed:
            raise ValueError("Confirm that this :free model is zero-cost before enabling free-only routing.")
        if not model.endswith(":free") and free_confirmed:
            raise ValueError("A paid UnoRouter model cannot be marked free or enabled for automatic routing.")
    elif not free_confirmed:
        raise ValueError("Confirm that this provider account and model are currently free.")
    with connect() as db:
        result = db.execute(
            "UPDATE provider_credentials SET model=?, free_confirmed=? WHERE provider=?",
            (model, int(free_confirmed), provider),
        )
        if result.rowcount == 0:
            raise ValueError("Save the provider API key before selecting its model.")

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
