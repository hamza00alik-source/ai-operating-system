"""Persistent company knowledge candidates with explicit source provenance."""
import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.knowledge_schemas import KnowledgeCreate, KnowledgeReview


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(row) -> dict:
    item = dict(row)
    item["tags"] = json.loads(item.pop("tags_json"))
    return item


def create_knowledge_item(payload: KnowledgeCreate, *, actor: str) -> dict:
    now = _now()
    item = {
        "id": str(uuid4()),
        "title": payload.title,
        "content": payload.content,
        "category": payload.category.lower(),
        "source_url": str(payload.source_url),
        "source_title": payload.source_title,
        "source_published_at": (
            payload.source_published_at.isoformat()
            if payload.source_published_at else None
        ),
        "source_accessed_at": now,
        "confidence": payload.confidence,
        "tags_json": json.dumps(payload.tags, separators=(",", ":")),
        "status": "candidate",
        "created_by": actor,
        "created_at": now,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
    }
    with connect() as db:
        db.execute(
            """INSERT INTO knowledge_items
            (id,title,content,category,source_url,source_title,source_published_at,
             source_accessed_at,confidence,tags_json,status,created_by,created_at,
             reviewed_by,reviewed_at,review_note)
            VALUES (:id,:title,:content,:category,:source_url,:source_title,
                    :source_published_at,:source_accessed_at,:confidence,:tags_json,
                    :status,:created_by,:created_at,:reviewed_by,:reviewed_at,:review_note)""",
            item,
        )
    return _decode(item)


def list_knowledge_items(
    *, limit: int = 100, status: str | None = None, category: str | None = None
) -> list[dict]:
    clauses, values = [], []
    if status:
        clauses.append("status=?")
        values.append(status)
    if category:
        clauses.append("category=?")
        values.append(category.strip().lower())
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM knowledge_items" + where
            + " ORDER BY created_at DESC LIMIT ?",
            (*values, limit),
        ).fetchall()
    return [_decode(row) for row in rows]


def get_knowledge_item(item_id: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
        ).fetchone()
    return _decode(row) if row else None


def review_knowledge_item(
    item_id: str, payload: KnowledgeReview, *, actor: str
) -> dict | None:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "candidate":
            raise ValueError("Only candidate knowledge can be reviewed once.")
        now = _now()
        changed = db.execute(
            """UPDATE knowledge_items
               SET status=?,reviewed_by=?,reviewed_at=?,review_note=?
               WHERE id=? AND status='candidate'""",
            (payload.decision, actor, now, payload.note, item_id),
        ).rowcount
        if changed != 1:
            raise ValueError("Knowledge candidate changed concurrently; reload and retry.")
        updated = db.execute(
            "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
        ).fetchone()
    return _decode(updated)


def retrieve_accepted_knowledge(query: str, *, limit: int = 5,
                                max_content_chars: int = 1200) -> list[dict]:
    """Return a small keyword-ranked context set from owner-accepted records only.

    This is deliberately lexical and local: no embeddings, external calls, or
    candidate/rejected records. Retrieved text remains untrusted reference data.
    """
    import re

    terms = {
        term for term in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", query.lower())
        if term not in {"the", "and", "for", "with", "from", "that", "this"}
    }
    accepted = list_knowledge_items(status="accepted", limit=500)
    ranked = []
    for item in accepted:
        haystack = " ".join([
            item["title"], item["content"], item["category"],
            item["source_title"], " ".join(item["tags"]),
        ]).lower()
        item_terms = set(re.findall(r"[a-z0-9][a-z0-9_-]{2,}", haystack))
        score = len(terms & item_terms)
        if score:
            ranked.append((score, item["created_at"], item))
    ranked.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return [
        {**item, "content": item["content"][:max_content_chars]}
        for _, _, item in ranked[:max(0, min(limit, 20))]
    ]
