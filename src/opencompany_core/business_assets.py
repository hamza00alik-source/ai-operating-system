"""Append-only, business-scoped asset declarations and safety lifecycle."""
from __future__ import annotations
import hashlib, json, re, sqlite3
from contextlib import contextmanager
from datetime import timezone
from pathlib import PurePosixPath
from uuid import uuid4
from .domain import AuditRecord
from .business_units import BusinessUnitRegistry

_HASH = re.compile(r"^[a-f0-9]{64}$")
_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_BUSINESS = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

class BusinessAssetRegistry:
    def __init__(self, connection: sqlite3.Connection, lock):
        self.connection, self.lock = connection, lock
        self.business_units = BusinessUnitRegistry(connection, lock)
        with lock:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS opencompany_business_assets (
              asset_id TEXT PRIMARY KEY, business_id TEXT NOT NULL, asset_key TEXT NOT NULL,
              title TEXT NOT NULL, asset_type TEXT NOT NULL, filename TEXT NOT NULL,
              media_type TEXT NOT NULL, checksum_sha256 TEXT NOT NULL, byte_size INTEGER NOT NULL,
              source TEXT NOT NULL, storage_state TEXT NOT NULL, status TEXT NOT NULL,
              storage_key TEXT, asset_scope_id TEXT NOT NULL, file_bytes_received INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, UNIQUE(business_id,asset_key));
            CREATE TABLE IF NOT EXISTS opencompany_business_asset_events (
              event_id TEXT PRIMARY KEY, business_id TEXT NOT NULL, asset_id TEXT NOT NULL,
              action TEXT NOT NULL, occurred_at TEXT NOT NULL, audit_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_business_asset_scan_events (
              event_id TEXT PRIMARY KEY, business_id TEXT NOT NULL, asset_id TEXT NOT NULL,
              scanner_key TEXT NOT NULL, status TEXT NOT NULL, checksum_sha256 TEXT NOT NULL,
              byte_size INTEGER NOT NULL, verdict TEXT NOT NULL, occurred_at TEXT NOT NULL,
              audit_json TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS opencompany_assets_no_delete BEFORE DELETE ON opencompany_business_assets
              BEGIN SELECT RAISE(ABORT,'append-only asset declarations'); END;
            CREATE TRIGGER IF NOT EXISTS opencompany_assets_no_update BEFORE UPDATE ON opencompany_business_assets
              WHEN OLD.asset_id != NEW.asset_id OR OLD.business_id != NEW.business_id OR OLD.asset_key != NEW.asset_key
                OR OLD.title != NEW.title OR OLD.asset_type != NEW.asset_type OR OLD.filename != NEW.filename
                OR OLD.media_type != NEW.media_type OR OLD.checksum_sha256 != NEW.checksum_sha256
                OR OLD.byte_size != NEW.byte_size OR OLD.source != NEW.source OR OLD.asset_scope_id != NEW.asset_scope_id
              BEGIN SELECT RAISE(ABORT,'asset declaration metadata is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS opencompany_asset_events_no_update BEFORE UPDATE ON opencompany_business_asset_events
              BEGIN SELECT RAISE(ABORT,'append-only asset events'); END;
            CREATE TRIGGER IF NOT EXISTS opencompany_asset_events_no_delete BEFORE DELETE ON opencompany_business_asset_events
              BEGIN SELECT RAISE(ABORT,'append-only asset events'); END;
            CREATE TRIGGER IF NOT EXISTS opencompany_asset_scan_events_no_update BEFORE UPDATE ON opencompany_business_asset_scan_events
              BEGIN SELECT RAISE(ABORT,'append-only scan events'); END;
            CREATE TRIGGER IF NOT EXISTS opencompany_asset_scan_events_no_delete BEFORE DELETE ON opencompany_business_asset_scan_events
              BEGIN SELECT RAISE(ABORT,'append-only scan events'); END;
            """)
            connection.commit()

    @contextmanager
    def _transaction(self):
        """Keep asset state and its audit event in one durable commit."""
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.commit()
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    @staticmethod
    def _audit_dict(audit):
        if not isinstance(audit, AuditRecord):
            raise ValueError("a valid audit record is required")
        return {"id":str(audit.id),"occurred_at":audit.occurred_at.astimezone(timezone.utc).isoformat(),
          "actor_type":audit.actor_type,"actor_id":audit.actor_id,"action":audit.action,
          "subject_type":audit.subject_type,"subject_id":audit.subject_id,"outcome":audit.outcome,
          "correlation_id":audit.correlation_id,"details":audit.details}

    def _event(self, business_id, asset_id, action, audit, scan=False, **fields):
        target = "opencompany_business_asset_scan_events" if scan else "opencompany_business_asset_events"
        payload = self._audit_dict(audit)
        if scan:
            self.connection.execute(f"""INSERT INTO {target}
              (event_id,business_id,asset_id,scanner_key,status,checksum_sha256,byte_size,verdict,occurred_at,audit_json)
              VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (str(uuid4()),business_id,asset_id,fields["scanner_key"],fields["status"],fields["checksum_sha256"],
               fields["byte_size"],fields["verdict"],payload["occurred_at"],json.dumps(payload,sort_keys=True)))
        else:
            self.connection.execute(f"""INSERT INTO {target}
              (event_id,business_id,asset_id,action,occurred_at,audit_json) VALUES(?,?,?,?,?,?)""",
              (str(uuid4()),business_id,asset_id,action,payload["occurred_at"],json.dumps(payload,sort_keys=True)))

    def _get(self,business_id,asset_id):
        self.business_units.require_active(business_id)
        row=self.connection.execute("SELECT * FROM opencompany_business_assets WHERE business_id=? AND asset_id=?",(business_id,str(asset_id))).fetchone()
        if row is None: raise ValueError("business asset not found")
        return dict(row)

    def declare(self,business_id,*,asset_key,title,asset_type,filename,media_type,checksum_sha256,byte_size,source,audit):
        if not isinstance(business_id,str) or not _BUSINESS.fullmatch(business_id): raise ValueError("invalid business identity")
        self.business_units.require_active(business_id)
        if not isinstance(asset_key,str) or not _KEY.fullmatch(asset_key): raise ValueError("invalid asset key")
        if not isinstance(title,str) or not title.strip() or len(title)>200: raise ValueError("invalid asset title")
        if not isinstance(filename,str) or filename in (".","..") or PurePosixPath(filename).name!=filename or "/" in filename or "\\" in filename: raise ValueError("unsafe asset filename")
        if not isinstance(checksum_sha256,str) or not _HASH.fullmatch(checksum_sha256): raise ValueError("invalid SHA-256 checksum")
        if not isinstance(byte_size,int) or isinstance(byte_size,bool) or not 0<=byte_size<=104857600: raise ValueError("invalid asset size")
        if not all(isinstance(x,str) and x.strip() for x in (asset_type,media_type,source)): raise ValueError("asset metadata is required")
        payload=self._audit_dict(audit)
        if audit.actor_type!="owner": raise PermissionError("only the owner may declare business assets")
        asset_id=str(uuid4()); scope=hashlib.sha256((business_id+"\0"+asset_id).encode()).hexdigest()
        with self.lock, self._transaction():
            self.connection.execute("""INSERT INTO opencompany_business_assets
              (asset_id,business_id,asset_key,title,asset_type,filename,media_type,checksum_sha256,byte_size,source,
               storage_state,status,storage_key,asset_scope_id,file_bytes_received,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?, 'metadata_only','declared',NULL,?,0,?)""",
              (asset_id,business_id,asset_key,title.strip(),asset_type,filename,media_type,checksum_sha256,byte_size,source,scope,payload["occurred_at"]))
            self._event(business_id,asset_id,"declared",audit)
            result=self._get(business_id,asset_id)
            result["file_bytes_received"] = bool(result["file_bytes_received"])
            return result

    def list(self,business_id):
        self.business_units.require_active(business_id)
        with self.lock:
            rows=self.connection.execute("SELECT * FROM opencompany_business_assets WHERE business_id=? ORDER BY created_at,asset_id",(business_id,)).fetchall()
        return tuple({**dict(r),"file_bytes_received":bool(r["file_bytes_received"])} for r in rows)

    def events(self,business_id,asset_id):
        self.business_units.require_active(business_id)
        with self.lock:
            rows=self.connection.execute("SELECT action,occurred_at,audit_json FROM opencompany_business_asset_events WHERE business_id=? AND asset_id=? ORDER BY rowid",(business_id,str(asset_id))).fetchall()
        return tuple({"action":r["action"],"occurred_at":r["occurred_at"],"audit":json.loads(r["audit_json"])} for r in rows)

    def storage_declaration(self,business_id,asset_id):
        with self.lock:
            item=self._get(business_id,asset_id)
        if item["storage_key"] is not None: raise ValueError("asset has already been stored")
        return {"business_id":business_id,"asset_id":item["asset_id"],"asset_scope_id":item["asset_scope_id"],
          "checksum_sha256":item["checksum_sha256"],"byte_size":item["byte_size"],"media_type":item["media_type"]}

    def record_storage(self,business_id,asset_id,*,storage_key,checksum_sha256,byte_size,audit):
        with self.lock, self._transaction():
            item=self._get(business_id,asset_id)
            if item["storage_key"] is not None: raise ValueError("asset has already been stored")
            if checksum_sha256 != item["checksum_sha256"] or byte_size != item["byte_size"]: raise ValueError("stored asset checksum or size does not match declaration")
            expected_prefix = hashlib.sha256((business_id + "\0" + item["asset_scope_id"]).encode("utf-8")).hexdigest()
            expected_storage_key = expected_prefix + "/" + item["asset_id"] + ".blob"
            if not isinstance(storage_key, str) or storage_key != expected_storage_key:
                raise ValueError("storage key does not match this business asset's private scope")
            if audit.actor_type != "owner": raise PermissionError("only the owner may record asset storage")
            self._audit_dict(audit)
            self.connection.execute("UPDATE opencompany_business_assets SET storage_key=?,storage_state='private_stored_unscanned',status='pending_scan' WHERE business_id=? AND asset_id=?",(storage_key,business_id,item["asset_id"]))
            self._event(business_id,item["asset_id"],"stored_unscanned",audit)
            return {**self._get(business_id,item["asset_id"]),"download_enabled":False}

    def scan_declaration(self,business_id,asset_id):
        with self.lock:
            item=self._get(business_id,asset_id)
        if item["storage_key"] is None or item["storage_state"]!="private_stored_unscanned": raise ValueError("asset is not awaiting scan")
        return {"business_id":business_id,"asset_id":item["asset_id"],"storage_key":item["storage_key"],
          "checksum_sha256":item["checksum_sha256"],"byte_size":item["byte_size"]}

    def record_scan_result(self,business_id,asset_id,*,scanner_key,status,checksum_sha256,byte_size,verdict,audit):
        if status not in ("clean","infected"): raise ValueError("invalid malware scan status")
        if not isinstance(scanner_key,str) or not scanner_key.strip(): raise ValueError("scanner identity is required")
        if not isinstance(verdict,str) or (status=="clean" and not verdict.endswith(": OK")) or (status=="infected" and not verdict.endswith(" FOUND")):
            raise ValueError("scanner verdict does not match the recorded status")
        with self.lock, self._transaction():
            item=self._get(business_id,asset_id)
            if item["storage_state"]!="private_stored_unscanned": raise ValueError("asset is not awaiting scan")
            if checksum_sha256 != item["checksum_sha256"] or byte_size != item["byte_size"]: raise ValueError("scan checksum and size do not match stored asset")
            if audit.actor_type!="system": raise PermissionError("scan verdict must be recorded by system actor")
            self._audit_dict(audit)
            if status=="clean":
                state,task,action="private_scanned_clean","pending_delivery_approval","scan_clean"
            else:
                state,task,action="quarantined","quarantined","scan_infected"
            self.connection.execute("UPDATE opencompany_business_assets SET storage_state=?,status=? WHERE business_id=? AND asset_id=?",(state,task,business_id,item["asset_id"]))
            self._event(business_id,item["asset_id"],action,audit)
            self._event(business_id,item["asset_id"],action,audit,scan=True,scanner_key=scanner_key,status=status,checksum_sha256=checksum_sha256,byte_size=byte_size,verdict=verdict)
            return {**self._get(business_id,item["asset_id"]),"download_enabled":False}
