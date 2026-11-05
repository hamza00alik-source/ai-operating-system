"""Append-only, hash-chained SQLite audit trail."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect

GENESIS = "0" * 64

def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _event_hash(previous_hash: str, event: dict) -> str:
    return hashlib.sha256((previous_hash + _canonical(event)).encode("utf-8")).hexdigest()

def append_event(actor: str, action: str, resource_type: str, resource_id: str, details: dict) -> dict:
    """Append one event in a serialized SQLite transaction; existing rows are never updated."""
    event = {
        "id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
    }
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        tail = db.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = tail["event_hash"] if tail else GENESIS
        digest = _event_hash(previous_hash, event)
        db.execute(
            """INSERT INTO audit_events
            (id,timestamp,actor,action,resource_type,resource_id,details_json,previous_hash,event_hash)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (event["id"], event["timestamp"], event["actor"], event["action"],
             event["resource_type"], event["resource_id"], _canonical(details),
             previous_hash, digest),
        )
    return {**event, "previous_hash": previous_hash, "event_hash": digest}

def list_events(limit: int = 100) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """SELECT id,timestamp,actor,action,resource_type,resource_id,
               details_json,previous_hash,event_hash
               FROM audit_events ORDER BY sequence DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [{
        "id": row["id"], "timestamp": row["timestamp"], "actor": row["actor"],
        "action": row["action"], "resource_type": row["resource_type"],
        "resource_id": row["resource_id"], "details": json.loads(row["details_json"]),
        "previous_hash": row["previous_hash"], "event_hash": row["event_hash"],
    } for row in rows]

def verify_chain() -> dict:
    with connect() as db:
        rows = db.execute(
            """SELECT id,timestamp,actor,action,resource_type,resource_id,
               details_json,previous_hash,event_hash
               FROM audit_events ORDER BY sequence ASC"""
        ).fetchall()
    previous_hash = GENESIS
    for index, row in enumerate(rows, start=1):
        event = {
            "id": row["id"], "timestamp": row["timestamp"], "actor": row["actor"],
            "action": row["action"], "resource_type": row["resource_type"],
            "resource_id": row["resource_id"], "details": json.loads(row["details_json"]),
        }
        if row["previous_hash"] != previous_hash:
            return {"valid": False, "checked_events": index - 1, "broken_at": index}
        expected = _event_hash(previous_hash, event)
        if row["event_hash"] != expected:
            return {"valid": False, "checked_events": index - 1, "broken_at": index}
        previous_hash = row["event_hash"]
    return {"valid": True, "checked_events": len(rows), "broken_at": None}
