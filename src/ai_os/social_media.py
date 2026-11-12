"""Owner-supervised social content and video brief workspace.

This module stores drafts and creative briefs only. It never publishes, schedules,
uploads media, invokes paid generation, or sends external requests.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from ai_os.db import connect

CHANNELS = {"instagram", "facebook", "tiktok", "youtube", "linkedin", "x", "pinterest", "threads"}
CONTENT_TYPES = {"post", "reel", "short", "story", "video", "carousel"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def initialize():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS social_content (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                channels_json TEXT NOT NULL DEFAULT '[]',
                content_type TEXT NOT NULL DEFAULT 'post',
                brief_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'draft',
                approval_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_social_content_status ON social_content(status, created_at)")


def create_content(*, kind, title, body="", channels=None, content_type="post", brief=None):
    initialize()
    channels = channels or []
    if kind not in {"social_post", "video_brief"}:
        raise ValueError("Unsupported content kind.")
    if not title.strip():
        raise ValueError("A title is required.")
    invalid = sorted(set(channels) - CHANNELS)
    if invalid:
        raise ValueError("Unsupported channels: " + ", ".join(invalid))
    if content_type not in CONTENT_TYPES:
        raise ValueError("Unsupported content type.")
    item_id, now = str(uuid.uuid4()), _now()
    with connect() as db:
        db.execute(
            """INSERT INTO social_content
            (id,kind,title,body,channels_json,content_type,brief_json,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,'draft',?,?)""",
            (item_id, kind, title.strip(), body.strip(), json.dumps(channels),
             content_type, json.dumps(brief or {}, ensure_ascii=False), now, now),
        )
    return get_content(item_id)


def get_content(item_id):
    initialize()
    with connect() as db:
        row = db.execute("SELECT * FROM social_content WHERE id=?", (item_id,)).fetchone()
    return _serialize(row) if row else None


def list_content(kind=None):
    initialize()
    with connect() as db:
        if kind:
            rows = db.execute("SELECT * FROM social_content WHERE kind=? ORDER BY created_at DESC", (kind,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM social_content ORDER BY created_at DESC").fetchall()
    return [_serialize(row) for row in rows]


def attach_approval(item_id, approval_id):
    with connect() as db:
        db.execute(
            "UPDATE social_content SET status='awaiting_approval', approval_id=?, updated_at=? WHERE id=?",
            (approval_id, _now(), item_id),
        )
    return get_content(item_id)


def set_decision(item_id, decision):
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    status = "approved_for_scheduling" if decision == "approved" else "rejected"
    with connect() as db:
        cursor = db.execute(
            "UPDATE social_content SET status=?, updated_at=? WHERE id=?",
            (status, _now(), item_id),
        )
        if cursor.rowcount == 0:
            return None
    return get_content(item_id)


def integration_status():
    return {
        "metricool": {
            "configured": bool(os.getenv("METRICOOL_API_TOKEN") and os.getenv("METRICOOL_USER_ID") and os.getenv("METRICOOL_BLOG_ID")),
            "required_environment": ["METRICOOL_API_TOKEN", "METRICOOL_USER_ID", "METRICOOL_BLOG_ID"],
            "capabilities": ["account_connection_target", "analytics_target", "calendar_target"],
            "publishing_enabled": False,
            "note": "Credentials are not read from the dashboard and no publish API is called in this release."
        },
        "canva": {
            "configured": bool(os.getenv("CANVA_CLIENT_ID") and os.getenv("CANVA_CLIENT_SECRET")),
            "required_environment": ["CANVA_CLIENT_ID", "CANVA_CLIENT_SECRET"],
            "capabilities": ["design_workflow_target"],
            "generation_enabled": False,
            "note": "OAuth/app access and media export require a separately verified Canva integration."
        },
        "video_generation": {
            "configured": bool(os.getenv("FAL_KEY")),
            "required_environment": ["FAL_KEY"],
            "generation_enabled": False,
            "note": "Provider key presence is not proof of free quota; generation remains disabled until a cost and provider gate is implemented."
        },
    }


def _serialize(row):
    return {
        "id": row["id"], "kind": row["kind"], "title": row["title"],
        "body": row["body"], "channels": json.loads(row["channels_json"]),
        "content_type": row["content_type"], "brief": json.loads(row["brief_json"]),
        "status": row["status"], "approval_id": row["approval_id"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }
