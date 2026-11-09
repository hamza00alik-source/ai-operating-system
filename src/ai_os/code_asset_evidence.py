"""Owner-controlled evidence ledger for code asset provenance and licensing readiness."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect

EVIDENCE_TYPES = {
    "authorship", "contributor_rights", "upstream_source", "dependency_license",
    "license_notice", "secret_scan", "legal_review", "other",
}
EVIDENCE_STATES = {"pending", "accepted", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(row) -> dict:
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
    return item


def add_evidence(asset_id: str, evidence_type: str, title: str, description: str,
                 source_url: str = "", metadata: dict | None = None) -> dict:
    if evidence_type not in EVIDENCE_TYPES:
        raise ValueError("Unsupported evidence type.")
    title, description, source_url = title.strip(), description.strip(), source_url.strip()
    if not title or not description:
        raise ValueError("Evidence title and description are required.")
    if len(title) > 160 or len(description) > 5000 or len(source_url) > 1000:
        raise ValueError("Evidence fields exceed their allowed length.")
    if source_url and not source_url.startswith(("https://", "http://")):
        raise ValueError("Evidence source URL must use HTTP or HTTPS.")
    evidence_id, now = str(uuid4()), _now()
    with connect() as db:
        if db.execute("SELECT 1 FROM code_assets WHERE id=?", (asset_id,)).fetchone() is None:
            raise LookupError("Code asset not found.")
        db.execute(
            """INSERT INTO code_asset_evidence
            (id,asset_id,evidence_type,title,description,source_url,metadata_json,
             review_state,created_at,reviewed_at,review_note)
            VALUES (?,?,?,?,?,?,?,'pending',?,NULL,'')""",
            (evidence_id, asset_id, evidence_type, title, description, source_url,
             json.dumps(metadata or {}, ensure_ascii=False), now),
        )
        row = db.execute("SELECT * FROM code_asset_evidence WHERE id=?", (evidence_id,)).fetchone()
    return _decode(row)


def list_evidence(asset_id: str) -> list[dict]:
    with connect() as db:
        if db.execute("SELECT 1 FROM code_assets WHERE id=?", (asset_id,)).fetchone() is None:
            raise LookupError("Code asset not found.")
        rows = db.execute(
            "SELECT * FROM code_asset_evidence WHERE asset_id=? ORDER BY created_at DESC LIMIT 500",
            (asset_id,),
        ).fetchall()
    return [_decode(row) for row in rows]


def review_evidence(evidence_id: str, decision: str, note: str = "") -> dict:
    if decision not in EVIDENCE_STATES - {"pending"}:
        raise ValueError("Decision must be accepted or rejected.")
    note = note.strip()
    if len(note) > 2000:
        raise ValueError("Review note exceeds 2000 characters.")
    now = _now()
    with connect() as db:
        row = db.execute("SELECT * FROM code_asset_evidence WHERE id=?", (evidence_id,)).fetchone()
        if row is None:
            raise LookupError("Evidence record not found.")
        db.execute(
            "UPDATE code_asset_evidence SET review_state=?,reviewed_at=?,review_note=? WHERE id=?",
            (decision, now, note, evidence_id),
        )
        updated = db.execute("SELECT * FROM code_asset_evidence WHERE id=?", (evidence_id,)).fetchone()
    return _decode(updated)


def evidence_summary(asset_id: str) -> dict:
    records = list_evidence(asset_id)
    counts = {state: sum(1 for item in records if item["review_state"] == state)
              for state in ("pending", "accepted", "rejected")}
    # Accepted means owner-reviewed evidence, not independent legal verification.
    required = {"authorship", "contributor_rights", "upstream_source",
                "dependency_license", "license_notice", "secret_scan", "legal_review"}
    accepted_types = {item["evidence_type"] for item in records if item["review_state"] == "accepted"}
    return {
        "asset_id": asset_id,
        "record_count": len(records),
        "counts": counts,
        "required_evidence_types": sorted(required),
        "missing_accepted_types": sorted(required - accepted_types),
        "owner_review_complete": required.issubset(accepted_types),
        "interpretation": "Owner-reviewed evidence tracking only; not an independent audit, ownership certificate, or legal opinion.",
        "licensing_readiness": "blocked" if not required.issubset(accepted_types) else "requires-independent-review",
    }
