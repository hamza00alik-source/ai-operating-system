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
    if provider == "unorouter":
        if model.endswith(":free") and not free_confirmed:
            raise ValueError("Confirm that this :free model is zero-cost before enabling automatic free-only routing.")
        if not model.endswith(":free") and free_confirmed:
            raise ValueError("A paid UnoRouter model cannot be marked free or enabled for automatic routing.")
    elif not free_confirmed:
        raise ValueError("Confirm that this provider account and model are currently free.")
    encrypted = _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")
    with connect() as db:
        db.execute(
            """INSERT INTO provider_credentials(provider, encrypted_secret, model, base_url, free_confirmed)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET encrypted_secret=excluded.encrypted_secret,
               model=excluded.model, base_url=excluded.base_url, free_confirmed=excluded.free_confirmed""",
            (provider, encrypted, model, PROVIDER_ENDPOINTS[provider], int(free_confirmed)),
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


BUSINESS_INTEGRATION_PROVIDERS = {"wordpress", "woocommerce", "shopify", "meta", "tiktok", "paypal", "stripe", "marketplace", "other"}


def save_business_integration(business_id: str, provider: str, secret: str, config: dict | None = None) -> dict:
    """Store one business integration secret encrypted and never return its value."""
    from datetime import datetime, timezone
    from ai_os.brain import BUSINESS_IDS
    scope = (business_id or "").strip()
    provider_id = (provider or "").strip().lower()
    if scope not in BUSINESS_IDS or scope == "core":
        raise ValueError("Choose one of the three business environments.")
    if provider_id not in BUSINESS_INTEGRATION_PROVIDERS:
        raise ValueError("Unsupported business integration provider.")
    if not isinstance(secret, str) or len(secret) < 8 or len(secret) > 4096:
        raise ValueError("Integration secret must contain between 8 and 4096 characters.")
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("Integration configuration must be an object.")
    import json
    config_json = json.dumps(config, ensure_ascii=False)[:8000]
    now = datetime.now(timezone.utc).isoformat()
    vault = _fernet()
    encrypted = vault.encrypt(secret.encode("utf-8")).decode("ascii")
    encrypted_config = vault.encrypt(config_json.encode("utf-8")).decode("ascii")
    with connect() as db:
        db.execute("""INSERT INTO business_integration_credentials
            (business_id,provider,encrypted_secret,config_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(business_id,provider) DO UPDATE SET
            encrypted_secret=excluded.encrypted_secret,config_json=excluded.config_json,updated_at=excluded.updated_at""",
            (scope, provider_id, encrypted, encrypted_config, now, now))
    return {"business_id": scope, "provider": provider_id, "configured": True, "secret_returned": False, "updated_at": now}


def business_integration_statuses(business_id: str) -> list[dict]:
    from ai_os.brain import BUSINESS_IDS
    scope = (business_id or "").strip()
    if scope not in BUSINESS_IDS or scope == "core":
        raise ValueError("Choose one of the three business environments.")
    with connect() as db:
        rows = db.execute("""SELECT provider,created_at,updated_at FROM business_integration_credentials
            WHERE business_id=? ORDER BY provider""", (scope,)).fetchall()
    return [{"business_id": scope, "provider": row["provider"], "configured": True,
             "created_at": row["created_at"], "updated_at": row["updated_at"]} for row in rows]


def get_business_integration_credential(business_id: str, provider: str) -> dict | None:
    """Internal-only decryptor for future provider adapters; never expose through an API."""
    from ai_os.brain import BUSINESS_IDS
    scope = (business_id or "").strip()
    provider_id = (provider or "").strip().lower()
    if scope not in BUSINESS_IDS or scope == "core" or provider_id not in BUSINESS_INTEGRATION_PROVIDERS:
        raise ValueError("Unknown business integration scope or provider.")
    with connect() as db:
        row = db.execute("""SELECT encrypted_secret,config_json FROM business_integration_credentials
            WHERE business_id=? AND provider=?""", (scope, provider_id)).fetchone()
    if row is None:
        return None
    try:
        secret = _fernet().decrypt(row["encrypted_secret"].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialVaultUnavailable("Business integration credential cannot be decrypted.") from exc
    import json
    try:
        config = json.loads(_fernet().decrypt(row["config_json"].encode("ascii")).decode("utf-8"))
    except InvalidToken as exc:
        raise CredentialVaultUnavailable("Business integration configuration cannot be decrypted.") from exc
    return {"business_id": scope, "provider": provider_id, "secret": secret, "config": config}


def delete_business_integration(business_id: str, provider: str) -> bool:
    from ai_os.brain import BUSINESS_IDS
    scope = (business_id or "").strip()
    provider_id = (provider or "").strip().lower()
    if scope not in BUSINESS_IDS or scope == "core" or provider_id not in BUSINESS_INTEGRATION_PROVIDERS:
        raise ValueError("Unknown business integration scope or provider.")
    with connect() as db:
        cur = db.execute("DELETE FROM business_integration_credentials WHERE business_id=? AND provider=?",
                         (scope, provider_id))
    return bool(cur.rowcount)
