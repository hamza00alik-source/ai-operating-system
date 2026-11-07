"""Owner-reviewed training examples and deterministic JSONL dataset exports."""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.training_schemas import TrainingExampleCreate, TrainingExampleReview

_SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_training_text(payload: TrainingExampleCreate) -> None:
    for field in (payload.system_prompt, payload.user_input, payload.ideal_response, *payload.source_refs):
        if any(pattern.search(field) for pattern in _SENSITIVE_PATTERNS):
            raise ValueError(
                "Training text appears to contain a credential or personal email address; remove it before storing."
            )


def _decode_example(row) -> dict:
    item = dict(row)
    item["source_refs"] = json.loads(item.pop("source_refs_json"))
    item["rights_confirmed"] = bool(item["rights_confirmed"])
    item["privacy_reviewed"] = bool(item["privacy_reviewed"])
    return item


def create_training_example(payload: TrainingExampleCreate, *, actor: str) -> dict:
    """Store a candidate; no example becomes trainable without a separate owner review."""
    _check_training_text(payload)
    item = {
        "id": str(uuid4()),
        "task_family": payload.task_family.strip().lower().replace(" ", "_"),
        "system_prompt": payload.system_prompt.strip(),
        "user_input": payload.user_input.strip(),
        "ideal_response": payload.ideal_response.strip(),
        "source_refs_json": json.dumps(payload.source_refs, separators=(",", ":")),
        "rights_confirmed": 1,
        "privacy_reviewed": 1,
        "status": "candidate",
        "created_by": actor,
        "created_at": _now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO model_training_examples
               (id,task_family,system_prompt,user_input,ideal_response,source_refs_json,
                rights_confirmed,privacy_reviewed,status,created_by,created_at)
               VALUES (:id,:task_family,:system_prompt,:user_input,:ideal_response,
                       :source_refs_json,:rights_confirmed,:privacy_reviewed,:status,
                       :created_by,:created_at)""",
            item,
        )
        row = db.execute(
            "SELECT * FROM model_training_examples WHERE id=?", (item["id"],)
        ).fetchone()
    return _decode_example(row)


def list_training_examples(*, status: str | None = None, limit: int = 100) -> list[dict]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Training example limit must be between 1 and 500.")
    if status is not None and status not in {"candidate", "accepted", "rejected"}:
        raise ValueError("Unsupported training example status.")
    query = "SELECT * FROM model_training_examples"
    params: list[object] = []
    if status:
        query += " WHERE status=?"
        params.append(status)
    query += " ORDER BY created_at DESC,id DESC LIMIT ?"
    params.append(limit)
    with connect() as db:
        rows = db.execute(query, params).fetchall()
    return [_decode_example(row) for row in rows]


def review_training_example(
    example_id: str, payload: TrainingExampleReview, *, actor: str
) -> dict | None:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM model_training_examples WHERE id=?", (example_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "candidate":
            raise ValueError("Training example has already been reviewed.")
        now = _now()
        changed = db.execute(
            """UPDATE model_training_examples
               SET status=?,reviewed_by=?,reviewed_at=?,review_note=?
               WHERE id=? AND status='candidate'""",
            (payload.decision, actor, now, payload.note.strip(), example_id),
        ).rowcount
        if changed != 1:
            raise ValueError("Training example was reviewed concurrently.")
        updated = db.execute(
            "SELECT * FROM model_training_examples WHERE id=?", (example_id,)
        ).fetchone()
    return _decode_example(updated)


def export_training_dataset(*, actor: str, limit: int = 500) -> dict:
    """Create a versioned JSONL export from accepted examples only."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError("Training dataset export limit must be between 1 and 1000.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            """SELECT * FROM model_training_examples WHERE status='accepted'
               ORDER BY task_family ASC,created_at ASC,id ASC LIMIT ?""",
            (limit,),
        ).fetchall()
        if not rows:
            raise ValueError("No owner-accepted training examples are available to export.")
        examples = [_decode_example(row) for row in rows]
        lines = []
        counts = Counter()
        for item in examples:
            counts[item["task_family"]] += 1
            record = {
                "messages": [
                    {"role": "system", "content": item["system_prompt"]},
                    {"role": "user", "content": item["user_input"]},
                    {"role": "assistant", "content": item["ideal_response"]},
                ],
                "metadata": {
                    "example_id": item["id"],
                    "task_family": item["task_family"],
                    "source_refs": item["source_refs"],
                },
            }
            lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        jsonl = "\n".join(lines) + "\n"
        digest = hashlib.sha256(jsonl.encode("utf-8")).hexdigest()
        version = db.execute(
            "SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM training_dataset_exports"
        ).fetchone()["next_version"]
        export = {
            "id": str(uuid4()),
            "version_number": version,
            "dataset_sha256": digest,
            "example_count": len(examples),
            "task_family_counts_json": json.dumps(dict(sorted(counts.items())), separators=(",", ":")),
            "example_ids_json": json.dumps([item["id"] for item in examples], separators=(",", ":")),
            "created_by": actor,
            "created_at": _now(),
        }
        db.execute(
            """INSERT INTO training_dataset_exports
               (id,version_number,dataset_sha256,example_count,task_family_counts_json,
                example_ids_json,created_by,created_at)
               VALUES (:id,:version_number,:dataset_sha256,:example_count,
                       :task_family_counts_json,:example_ids_json,:created_by,:created_at)""",
            export,
        )
    return {
        "export_id": export["id"],
        "version_number": version,
        "dataset_sha256": digest,
        "example_count": len(examples),
        "task_family_counts": dict(sorted(counts.items())),
        "example_ids": [item["id"] for item in examples],
        "created_by": actor,
        "created_at": export["created_at"],
        "format": "chat_messages_jsonl_with_metadata",
        "jsonl": jsonl,
        "limitations": [
            "Export includes only owner-accepted examples with rights/privacy attestations.",
            "The owner attestations and basic pattern scan are not a legal review or complete PII detector.",
            "Exporting data does not train, fine-tune, download, or deploy a model.",
            "Keep the returned dataset private; do not commit it or customer data to the public repository.",
        ],
    }


def list_training_dataset_exports(*, limit: int = 50) -> list[dict]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise ValueError("Dataset export history limit must be between 1 and 200.")
    with connect() as db:
        rows = db.execute(
            """SELECT id,version_number,dataset_sha256,example_count,
                      task_family_counts_json,example_ids_json,created_by,created_at
               FROM training_dataset_exports ORDER BY version_number DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["task_family_counts"] = json.loads(item.pop("task_family_counts_json"))
        item["example_ids"] = json.loads(item.pop("example_ids_json"))
        results.append(item)
    return results
