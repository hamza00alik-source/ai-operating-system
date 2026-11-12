"""Owner-managed metadata registry for business-isolated assets.

This module declares ownership and provenance only. It does not upload, scan,
store, expose, or deliver file bytes.
"""
from __future__ import annotations
import re
import json
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4
from .persistence import _audit_payload, _digest, _json, _ZERO_HASH

_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_MEDIA = re.compile(r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,254}$")

class BusinessAssetRegistry:
    """Asset metadata is always queried through a single trusted business scope."""
    def __init__(self, connection: sqlite3.Connection, lock: RLock):
        self._db, self._lock = connection, lock

    def _scope(self, business_id: str) -> str:
        if not isinstance(business_id,str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}",business_id):
            raise ValueError("business_id must be a 2-63 character lowercase slug")
        with self._lock:
            row=self._db.execute("SELECT asset_scope_id FROM opencompany_business_units WHERE business_id=?",(business_id,)).fetchone()
        if row is None: raise ValueError("unknown business unit")
        return row["asset_scope_id"]

    @staticmethod
    def _validate(asset_key: str,title: str,asset_type: str,filename: str,media_type: str,
                  checksum_sha256: str,byte_size: int,source: str) -> None:
        if not isinstance(asset_key,str) or not _SLUG.fullmatch(asset_key): raise ValueError("invalid asset_key")
        if not isinstance(title,str) or not title.strip() or len(title)>200: raise ValueError("title must contain 1-200 characters")
        if not isinstance(asset_type,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}",asset_type): raise ValueError("invalid asset_type")
        if not isinstance(filename,str) or not _FILENAME.fullmatch(filename) or filename in {".",".."}:
            raise ValueError("filename must be a plain filename without path separators")
        if not isinstance(media_type,str) or not _MEDIA.fullmatch(media_type): raise ValueError("invalid media_type")
        if not isinstance(checksum_sha256,str) or not _SHA256.fullmatch(checksum_sha256): raise ValueError("checksum_sha256 must be lowercase SHA-256 hex")
        if not isinstance(byte_size,int) or isinstance(byte_size,bool) or not 0<=byte_size<=104857600:
            raise ValueError("byte_size must be between 0 and 104857600")
        if not isinstance(source,str) or not source.strip() or len(source)>500: raise ValueError("source must contain 1-500 characters")

    def declare(self,business_id: str,*,asset_key: str,title: str,asset_type: str,filename: str,
                media_type: str,checksum_sha256: str,byte_size: int,source: str,audit) -> dict[str,Any]:
        self._validate(asset_key,title,asset_type,filename,media_type,checksum_sha256,byte_size,source)
        if audit.actor_type!="owner": raise PermissionError("only owner-originated asset declarations are enabled")
        scope=self._scope(business_id); asset_id=str(uuid4()); event_id=str(uuid4())
        now=datetime.now(timezone.utc).isoformat()
        details={"asset_key":asset_key,"asset_type":asset_type,"filename":filename,
                 "media_type":media_type,"checksum_sha256":checksum_sha256,"byte_size":byte_size,
                 "storage_state":"metadata_only","file_bytes_received":False}
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("""INSERT INTO opencompany_business_assets
                    (asset_id,business_id,asset_scope_id,asset_key,title,asset_type,filename,media_type,
                     checksum_sha256,byte_size,source,storage_state,status,actor_type,actor_id,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,'metadata_only','pending_storage','owner',?,?)""",
                    (asset_id,business_id,scope,asset_key,title.strip(),asset_type,filename,media_type,
                     checksum_sha256,byte_size,source.strip(),audit.actor_id,now))
                self._db.execute("""INSERT INTO opencompany_business_asset_events
                    (event_id,asset_id,business_id,asset_scope_id,action,actor_type,actor_id,details_json,occurred_at)
                    VALUES(?,?,?,?,'declared','owner',?,?,?)""",
                    (event_id,asset_id,business_id,scope,audit.actor_id,_json(details),now))
                previous=self._db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash=previous["event_hash"] if previous else _ZERO_HASH
                from .domain import AuditRecord
                audited=AuditRecord(id=audit.id,occurred_at=audit.occurred_at,actor_type="owner",
                    actor_id=audit.actor_id,action=audit.action,subject_type="business_asset",
                    subject_id=f"{business_id}:{asset_key}",outcome="pending_storage",
                    correlation_id=audit.correlation_id,
                    details={"business_id":business_id,"asset_id":asset_id,"asset_key":asset_key,
                             "file_bytes_received":False})
                payload=_audit_payload(audited,previous_hash)
                self._db.execute("INSERT INTO audit_events(event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audited.id),audited.occurred_at.isoformat(),_json(payload),previous_hash,_digest(payload)))
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction: self._db.execute("ROLLBACK")
                raise
        return {"asset_id":asset_id,"business_id":business_id,"asset_key":asset_key,
                "title":title.strip(),"asset_type":asset_type,"filename":filename,"media_type":media_type,
                "checksum_sha256":checksum_sha256,"byte_size":byte_size,"source":source.strip(),
                "storage_state":"metadata_only","status":"pending_storage","created_at":now,
                "file_bytes_received":False}

    def list(self,business_id: str,*,limit: int=100) -> tuple[dict[str,Any],...]:
        if not 1<=limit<=500: raise ValueError("limit must be between 1 and 500")
        scope=self._scope(business_id)
        with self._lock:
            rows=self._db.execute("""SELECT asset_id,business_id,asset_key,title,asset_type,filename,media_type,
                checksum_sha256,byte_size,source,storage_state,status,created_at
                FROM opencompany_business_assets WHERE business_id=? AND asset_scope_id=?
                ORDER BY created_at DESC,asset_key LIMIT ?""",(business_id,scope,limit)).fetchall()
        return tuple(dict(row) for row in rows)

    def events(self,business_id: str,asset_id: str) -> tuple[dict[str,Any],...]:
        scope=self._scope(business_id)
        with self._lock:
            rows=self._db.execute("""SELECT event_id,asset_id,business_id,action,actor_type,actor_id,details_json,occurred_at
                FROM opencompany_business_asset_events WHERE business_id=? AND asset_scope_id=? AND asset_id=?
                ORDER BY occurred_at,event_id""",(business_id,scope,asset_id)).fetchall()
        return tuple({**dict(row),"details":json.loads(row["details_json"])} for row in rows)
