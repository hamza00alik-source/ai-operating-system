"""Authenticated encryption for owner-managed provider credentials.

Secrets are encrypted with AES-256-GCM before SQLite persistence. The
dedicated OPENCOMPANY_SECRET_ENCRYPTION_KEY is required; there is no owner-key
fallback. Keep it stable and backed up; rotating it requires re-entering
provider credentials.
"""
from __future__ import annotations
import json, os, re, secrets, sqlite3
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from .domain import AuditRecord

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
        if len(value) < 32:
            raise SecretVaultError(
                "Set a dedicated OPENCOMPANY_SECRET_ENCRYPTION_KEY of at least 32 characters before saving or reading provider credentials."
            )
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


class BusinessCredentialVault:
    """Encrypted per-business credentials with scoped, append-only change history."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db, self._lock = connection, lock
        with self._lock:
            required = {"opencompany_business_credentials", "opencompany_business_credential_events"}
            present = {
                row["name"] for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not required.issubset(present):
                raise RuntimeError("business credential schema migration is required before vault initialization")

    def _unit(self, business_id: str) -> sqlite3.Row:
        if not isinstance(business_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", business_id):
            raise ValueError("business_id must be a valid registered business slug")
        row = self._db.execute(
            "SELECT business_id,credential_scope_id,status FROM opencompany_business_units WHERE business_id=?",
            (business_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown business unit")
        return row

    @staticmethod
    def _cipher() -> AESGCM:
        key = HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=ProviderSecretVault._SALT,
            info=b"opencompany/aes-256-gcm/business-credentials",
        ).derive(ProviderSecretVault._key_material())
        return AESGCM(key)

    @staticmethod
    def _aad(business_id: str, scope_id: str, credential_key: str) -> bytes:
        return f"opencompany:business-credential:{business_id}:{scope_id}:{credential_key}:v1".encode()

    def _append_audit(self, audit: AuditRecord, *, business_id: str, credential_key: str,
                      action: str, revision: int) -> None:
        from .persistence import _ZERO_HASH, _audit_payload, _digest, _json

        previous = self._db.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else _ZERO_HASH
        details = dict(audit.details)
        details.update({
            "business_id": business_id, "credential_key": credential_key,
            "credential_action": action, "credential_revision": revision,
            "secret_material_recorded": False,
        })
        audited = AuditRecord(
            id=audit.id, occurred_at=audit.occurred_at, actor_type="owner",
            actor_id=audit.actor_id, action=audit.action,
            subject_type="business_credential", subject_id=f"{business_id}:{credential_key}",
            outcome=action, correlation_id=audit.correlation_id, details=details,
        )
        payload = _audit_payload(audited, previous_hash)
        self._db.execute(
            """INSERT INTO audit_events
               (event_id,occurred_at,payload_json,previous_hash,event_hash)
               VALUES(?,?,?,?,?)""",
            (str(audited.id), audited.occurred_at.isoformat(), _json(payload),
             previous_hash, _digest(payload)),
        )

    def put(self, business_id: str, credential_key: str, value: dict[str, str],
            audit: AuditRecord) -> int:
        if audit.actor_type != "owner":
            raise PermissionError("business credentials can only be stored by the owner-authenticated API boundary")
        if not isinstance(credential_key, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{0,79}", credential_key
        ):
            raise ValueError("credential_key must be a lowercase identifier")
        if not isinstance(value, dict) or not 1 <= len(value) <= 20:
            raise ValueError("credential payload must contain 1-20 fields")
        if any(
            not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", key)
            or not isinstance(item, str) or not item.strip() or len(item) > 4096
            for key, item in value.items()
        ):
            raise ValueError("credential payload fields must be bounded non-empty strings")
        plaintext = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        if len(plaintext) > 16_000:
            raise ValueError("credential payload exceeds the 16000-byte limit")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                unit = self._unit(business_id)
                scope_id = unit["credential_scope_id"]
                prior = self._db.execute(
                    "SELECT revision,created_at FROM opencompany_business_credentials "
                    "WHERE business_id=? AND credential_key=?",
                    (business_id, credential_key),
                ).fetchone()
                revision = int(prior["revision"]) + 1 if prior else 1
                action = "rotated" if prior else "stored"
                nonce = secrets.token_bytes(12)
                ciphertext = self._cipher().encrypt(
                    nonce, plaintext, self._aad(business_id, scope_id, credential_key)
                )
                self._db.execute(
                    """INSERT INTO opencompany_business_credentials
                       (business_id,credential_scope_id,credential_key,nonce,ciphertext,
                        revision,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)
                       ON CONFLICT(business_id,credential_key) DO UPDATE SET
                       nonce=excluded.nonce,ciphertext=excluded.ciphertext,
                       revision=excluded.revision,updated_at=excluded.updated_at""",
                    (business_id, scope_id, credential_key, nonce, ciphertext, revision,
                     prior["created_at"] if prior else now, now),
                )
                self._db.execute(
                    """INSERT INTO opencompany_business_credential_events
                       (event_id,business_id,credential_scope_id,credential_key,action,
                        revision,actor_type,actor_id,occurred_at)
                       VALUES(?,?,?,?,?,?,'owner',?,?)""",
                    (str(uuid4()), business_id, scope_id, credential_key, action,
                     revision, audit.actor_id, now),
                )
                self._append_audit(audit, business_id=business_id, credential_key=credential_key,
                                   action=action, revision=revision)
                self._db.execute("COMMIT")
                return revision
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def get(self, business_id: str, credential_key: str) -> dict[str, str] | None:
        with self._lock:
            unit = self._unit(business_id)
            row = self._db.execute(
                """SELECT credential_scope_id,nonce,ciphertext FROM opencompany_business_credentials
                   WHERE business_id=? AND credential_key=?""",
                (business_id, credential_key),
            ).fetchone()
        if row is None:
            return None
        if row["credential_scope_id"] != unit["credential_scope_id"]:
            raise SecretVaultError("Credential record scope does not match its registered business unit.")
        try:
            raw = self._cipher().decrypt(
                bytes(row["nonce"]), bytes(row["ciphertext"]),
                self._aad(business_id, row["credential_scope_id"], credential_key),
            )
            value = json.loads(raw.decode())
            if not isinstance(value, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()
            ):
                raise ValueError("invalid credential payload")
            return value
        except Exception as exc:
            raise SecretVaultError("Business credential could not be decrypted; verify the stable server encryption key.") from exc

    def list_status(self, business_id: str) -> tuple[dict[str, object], ...]:
        with self._lock:
            self._unit(business_id)
            rows = self._db.execute(
                """SELECT credential_key,revision,created_at,updated_at
                   FROM opencompany_business_credentials WHERE business_id=?
                   ORDER BY credential_key""",
                (business_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def delete(self, business_id: str, credential_key: str, audit: AuditRecord) -> bool:
        if audit.actor_type != "owner":
            raise PermissionError("business credentials can only be removed by the owner-authenticated API boundary")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                unit = self._unit(business_id)
                row = self._db.execute(
                    """SELECT revision FROM opencompany_business_credentials
                       WHERE business_id=? AND credential_key=?""",
                    (business_id, credential_key),
                ).fetchone()
                if row is None:
                    self._db.execute("ROLLBACK")
                    return False
                revision = int(row["revision"])
                self._db.execute(
                    "DELETE FROM opencompany_business_credentials WHERE business_id=? AND credential_key=?",
                    (business_id, credential_key),
                )
                self._db.execute(
                    """INSERT INTO opencompany_business_credential_events
                       (event_id,business_id,credential_scope_id,credential_key,action,
                        revision,actor_type,actor_id,occurred_at)
                       VALUES(?,?,?,?,'deleted',?,'owner',?,?)""",
                    (str(uuid4()), business_id, unit["credential_scope_id"], credential_key,
                     revision, audit.actor_id, audit.occurred_at.isoformat()),
                )
                self._append_audit(audit, business_id=business_id, credential_key=credential_key,
                                   action="deleted", revision=revision)
                self._db.execute("COMMIT")
                return True
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
