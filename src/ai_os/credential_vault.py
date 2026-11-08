"""Encrypted, server-side integration credential vault.

Secrets are encrypted at rest and never returned by API read operations.
The encryption key must be supplied by the deployment environment.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from ai_os.db import connect

_PROVIDER = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_SECRET_TYPE = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
_MAX_SECRET_BYTES = 32_768


class CredentialVaultError(RuntimeError):
    pass


def _cipher() -> Fernet:
    key = os.getenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not key:
        raise CredentialVaultError(
            "Credential vault is locked. Configure AI_OS_CREDENTIAL_ENCRYPTION_KEY in the server secret environment."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise CredentialVaultError("Credential encryption key is invalid; vault remains locked.") from exc


def initialize_credential_vault() -> None:
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS integration_credentials (
                credential_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                label TEXT NOT NULL,
                secret_type TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked_at TEXT
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_integration_credentials_provider
            ON integration_credentials(provider_id, created_at)
        """)


def store_credential(*, provider_id: str, label: str, secret_type: str, secret: dict) -> dict:
    provider_id = provider_id.strip().lower()
    label = label.strip()
    secret_type = secret_type.strip().lower()
    if not _PROVIDER.fullmatch(provider_id):
        raise ValueError("provider_id must be a lowercase provider identifier.")
    if not label or len(label) > 100:
        raise ValueError("Credential label must contain 1 to 100 characters.")
    if not _SECRET_TYPE.fullmatch(secret_type):
        raise ValueError("secret_type must be a short lowercase identifier.")
    if not isinstance(secret, dict) or not secret:
        raise ValueError("secret must be a non-empty object.")
    plaintext = json.dumps(secret, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(plaintext) > _MAX_SECRET_BYTES:
        raise ValueError("Credential payload exceeds the 32 KiB limit.")
    ciphertext = _cipher().encrypt(plaintext)
    credential_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """INSERT INTO integration_credentials
               (credential_id, provider_id, label, secret_type, ciphertext, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (credential_id, provider_id, label, secret_type, ciphertext, now, now),
        )
    return {
        "credential_ref": "vault:" + credential_id,
        "provider_id": provider_id,
        "label": label,
        "secret_type": secret_type,
        "created_at": now,
        "status": "stored_encrypted",
    }


def list_credentials(*, provider_id: str | None = None) -> list[dict]:
    with connect() as db:
        if provider_id:
            rows = db.execute(
                """SELECT credential_id, provider_id, label, secret_type, created_at,
                          updated_at, revoked_at
                   FROM integration_credentials WHERE provider_id=? ORDER BY created_at DESC""",
                (provider_id,),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT credential_id, provider_id, label, secret_type, created_at,
                          updated_at, revoked_at
                   FROM integration_credentials ORDER BY created_at DESC"""
            ).fetchall()
    return [{
        **dict(row),
        "credential_ref": "vault:" + row["credential_id"],
        "status": "revoked" if row["revoked_at"] else "stored_encrypted",
    } for row in rows]


def resolve_credential(credential_ref: str) -> dict:
    if not isinstance(credential_ref, str) or not credential_ref.startswith("vault:"):
        raise CredentialVaultError("Credential reference is not a vault reference.")
    credential_id = credential_ref[6:]
    with connect() as db:
        row = db.execute(
            """SELECT ciphertext, revoked_at FROM integration_credentials
               WHERE credential_id=?""",
            (credential_id,),
        ).fetchone()
    if row is None or row["revoked_at"] is not None:
        raise CredentialVaultError("Credential is missing or revoked.")
    try:
        plaintext = _cipher().decrypt(bytes(row["ciphertext"]))
        value = json.loads(plaintext)
    except (InvalidToken, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialVaultError("Credential could not be decrypted; no fallback was attempted.") from exc
    if not isinstance(value, dict):
        raise CredentialVaultError("Stored credential payload is invalid.")
    return value


def revoke_credential(credential_ref: str) -> dict | None:
    if not isinstance(credential_ref, str) or not credential_ref.startswith("vault:"):
        raise ValueError("Credential reference must use vault:...")
    credential_id = credential_ref[6:]
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """UPDATE integration_credentials SET revoked_at=?, updated_at=?
               WHERE credential_id=? AND revoked_at IS NULL""",
            (now, now, credential_id),
        )
        row = db.execute(
            """SELECT credential_id, provider_id, label, secret_type, revoked_at
               FROM integration_credentials WHERE credential_id=?""",
            (credential_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        **dict(row),
        "credential_ref": "vault:" + row["credential_id"],
        "status": "revoked" if row["revoked_at"] else "stored_encrypted",
    }
