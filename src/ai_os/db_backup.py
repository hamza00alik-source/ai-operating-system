"""Safe SQLite backup and integrity verification helpers.

These helpers are intentionally not exposed as HTTP endpoints. Operators must
stop application writers before copying a backup off-host or restoring it.
"""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from ai_os.audit import GENESIS, _event_hash
from ai_os.db import _database_path


def _source_path() -> Path:
    raw = _database_path()
    if raw == ":memory:":
        raise ValueError("In-memory databases cannot be backed up.")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("The configured SQLite database does not exist.")
    return path


def verify_sqlite_backup(backup_path: str | Path) -> dict:
    """Run SQLite integrity_check and confirm the expected application schema."""
    path = Path(backup_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("Backup file does not exist.")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"tasks", "jobs", "company_runs", "company_run_steps",
                    "audit_events", "knowledge_items"}
        missing = sorted(required - tables)
        audit_valid = False
        audit_checked = 0
        if "audit_events" in tables:
            previous_hash = GENESIS
            audit_valid = True
            rows = db.execute(
                """SELECT id,timestamp,actor,action,resource_type,resource_id,
                          details_json,previous_hash,event_hash
                   FROM audit_events ORDER BY sequence ASC"""
            )
            for index, row in enumerate(rows, start=1):
                event = {
                    "id": row["id"], "timestamp": row["timestamp"],
                    "actor": row["actor"], "action": row["action"],
                    "resource_type": row["resource_type"],
                    "resource_id": row["resource_id"],
                    "details": json.loads(row["details_json"]),
                }
                if (row["previous_hash"] != previous_hash or
                        row["event_hash"] != _event_hash(previous_hash, event)):
                    audit_valid = False
                    break
                previous_hash = row["event_hash"]
                audit_checked = index
    return {
        "valid": integrity == ["ok"] and not missing and audit_valid,
        "integrity": integrity,
        "missing_tables": missing,
        "tables_checked": len(tables),
        "audit_chain_valid": audit_valid,
        "audit_events_checked": audit_checked,
    }


def create_database_backup(destination: str | Path) -> dict:
    """Create a consistent SQLite snapshot and atomically publish the backup file."""
    source = _source_path()
    target = Path(destination).expanduser().resolve()
    if target == source:
        raise ValueError("Backup destination must differ from the live database.")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with sqlite3.connect(str(source), timeout=30) as live:
            live.execute("PRAGMA busy_timeout=30000")
            with sqlite3.connect(str(temporary), timeout=30) as backup:
                live.backup(backup)
                backup.commit()
        verification = verify_sqlite_backup(temporary)
        if not verification["valid"]:
            raise RuntimeError(
                f"SQLite backup verification failed: {verification}"
            )
        os.replace(temporary, target)
        return {
            "path": str(target),
            "size_bytes": target.stat().st_size,
            "verification": verification,
        }
    finally:
        if temporary.exists():
            temporary.unlink()
