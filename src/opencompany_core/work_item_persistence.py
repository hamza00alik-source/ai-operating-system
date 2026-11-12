"""Work-item and deliverable persistence operations for SQLiteStore."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from uuid import UUID

from .domain import AuditRecord, TaskState, WorkItem
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json


class WorkItemPersistenceMixin:
    """Atomic task, deliverable and owner-review repository operations."""

    def save_work_item(self, item: WorkItem) -> None:
        with self._lock:
            existing = self._connection.execute(
                "SELECT business_id FROM work_items WHERE id=?", (str(item.id),)
            ).fetchone()
            if existing is not None and existing["business_id"] != item.business_id:
                raise ValueError("a work item's business unit is immutable")
            self._connection.execute(
                """INSERT INTO work_items
                   (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, objective=excluded.objective,
                     department=excluded.department, state=excluded.state,
                     assigned_agent_id=excluded.assigned_agent_id,
                     dependencies_json=excluded.dependencies_json,
                     created_at=excluded.created_at""",
                (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                 str(item.assigned_agent_id) if item.assigned_agent_id else None,
                 _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
            )

    def save_work_item_with_audit(self, item: WorkItem, record: AuditRecord) -> str:
        """Persist a work item change and its audit evidence in one transaction."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT business_id FROM work_items WHERE id=?", (str(item.id),)
                ).fetchone()
                if existing is not None and existing["business_id"] != item.business_id:
                    raise ValueError("a work item's business unit is immutable")
                self._connection.execute(
                    """INSERT INTO work_items
                       (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         title=excluded.title, objective=excluded.objective,
                         department=excluded.department, state=excluded.state,
                         assigned_agent_id=excluded.assigned_agent_id,
                         dependencies_json=excluded.dependencies_json,
                         created_at=excluded.created_at""",
                    (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                     str(item.assigned_agent_id) if item.assigned_agent_id else None,
                     _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                )
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def save_work_items_with_audit(
        self, items: tuple[WorkItem, ...], records: tuple[AuditRecord, ...]
    ) -> None:
        """Persist a complete draft plan and all audit events atomically."""
        if not items or len(items) != len(records):
            raise ValueError("each planned work item requires one audit record")
        if len({item.id for item in items}) != len(items):
            raise ValueError("planned work item identifiers must be unique")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    self._connection.execute(
                        """INSERT INTO work_items
                           (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (str(item.id), item.title, item.objective, item.department, item.business_id,
                         item.state.value, str(item.assigned_agent_id) if item.assigned_agent_id else None,
                         _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                    )
                for record in records:
                    row = self._connection.execute(
                        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    previous_hash = row["event_hash"] if row else _ZERO_HASH
                    payload = _audit_payload(record, previous_hash)
                    self._connection.execute(
                        """INSERT INTO audit_events
                           (event_id,occurred_at,payload_json,previous_hash,event_hash)
                           VALUES(?,?,?,?,?)""",
                        (str(record.id), record.occurred_at.isoformat(), _json(payload),
                         previous_hash, _digest(payload)),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def save(self, deliverable: Any) -> None:
        """Idempotently stage a review-required artifact before its atomic audit transition."""
        if not deliverable.review_required:
            raise ValueError("worker deliverables must require review")
        values = (
            str(deliverable.work_item_id), deliverable.role_key, deliverable.content,
            deliverable.provider, deliverable.model, float(deliverable.cost_usd),
            deliverable.created_at.isoformat(), 1,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute(
                    "SELECT state FROM work_items WHERE id=?", (str(deliverable.work_item_id),)
                ).fetchone()
                if item is None or item["state"] != TaskState.IN_PROGRESS.value:
                    raise ValueError("artifact can only be staged for an in-progress work item")
                existing = self._connection.execute(
                    "SELECT * FROM deliverables WHERE id=?", (str(deliverable.id),)
                ).fetchone()
                if existing is not None:
                    old = (
                        existing["work_item_id"], existing["role_key"], existing["content"],
                        existing["provider"], existing["model"], float(existing["cost_usd"]),
                        existing["created_at"], int(existing["review_required"]),
                    )
                    if old != values:
                        raise ValueError("deliverable ID already exists with different content")
                else:
                    self._connection.execute(
                        "INSERT INTO deliverables (id,work_item_id,role_key,content,provider,model,cost_usd,created_at,review_required) VALUES(?,?,?,?,?,?,?,?,?)",
                        (str(deliverable.id), *values),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def save_deliverable_with_audit(
        self, deliverable: Any, record: AuditRecord, *, expected_agent_id: UUID | None = None
    ) -> bool:
        """Persist a draft, move its task to review, and audit atomically.

        Worker writes are fenced against reassignment or agent deactivation in
        the same transaction as the deliverable and task update.
        """
        if not deliverable.review_required:
            raise ValueError("worker deliverables must require review")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if expected_agent_id is None:
                    item = self._connection.execute(
                        "SELECT state FROM work_items WHERE id=?", (str(deliverable.work_item_id),)
                    ).fetchone()
                    authorized = item is not None and item["state"] == TaskState.IN_PROGRESS.value
                else:
                    item = self._connection.execute(
                        """SELECT w.state,w.assigned_agent_id,a.state AS agent_state
                           FROM work_items w LEFT JOIN agent_profiles a ON a.id=w.assigned_agent_id
                           WHERE w.id=?""", (str(deliverable.work_item_id),)
                    ).fetchone()
                    authorized = (
                        item is not None
                        and item["state"] == TaskState.IN_PROGRESS.value
                        and item["assigned_agent_id"] == str(expected_agent_id)
                        and item["agent_state"] == "active"
                    )
                if not authorized:
                    self._connection.execute("ROLLBACK")
                    return False
                values = (str(deliverable.work_item_id), deliverable.role_key, deliverable.content, deliverable.provider, deliverable.model, float(deliverable.cost_usd), deliverable.created_at.isoformat(), 1)
                existing = self._connection.execute("SELECT * FROM deliverables WHERE id=?", (str(deliverable.id),)).fetchone()
                if existing is not None:
                    old = (existing["work_item_id"], existing["role_key"], existing["content"], existing["provider"], existing["model"], float(existing["cost_usd"]), existing["created_at"], int(existing["review_required"]))
                    if old != values:
                        raise ValueError("deliverable ID already exists with different content")
                else:
                    self._connection.execute("INSERT INTO deliverables (id,work_item_id,role_key,content,provider,model,cost_usd,created_at,review_required) VALUES(?,?,?,?,?,?,?,?,?)", (str(deliverable.id), *values))
                self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (TaskState.REVIEW.value, str(deliverable.work_item_id), TaskState.IN_PROGRESS.value))
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def review_work_item_with_audit(self, work_item_id: UUID, *, approved: bool, rationale: str, record: AuditRecord) -> TaskState | None:
        """Record an owner review decision and transition REVIEW atomically."""
        if not isinstance(approved, bool) or not rationale.strip() or len(rationale) > 2000:
            raise ValueError("review decision and a 1-2000 character rationale are required")
        target = TaskState.COMPLETED if approved else TaskState.READY
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute("SELECT state FROM work_items WHERE id=?", (str(work_item_id),)).fetchone()
                if item is None or item["state"] != TaskState.REVIEW.value:
                    self._connection.execute("ROLLBACK")
                    return None
                count = self._connection.execute("SELECT COUNT(*) AS n FROM deliverables WHERE work_item_id=? AND review_required=1", (str(work_item_id),)).fetchone()["n"]
                if int(count) < 1:
                    self._connection.execute("ROLLBACK")
                    raise ValueError("work item has no review-required deliverable")
                self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (target.value, str(work_item_id), TaskState.REVIEW.value))
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return target
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
    def fail_work_item_with_audit(self, work_item_id: UUID, record: AuditRecord) -> bool:
        """Move an in-progress task to failed only after its queue exhausts retries."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (TaskState.FAILED.value, str(work_item_id), TaskState.IN_PROGRESS.value))
                if cursor.rowcount != 1:
                    self._connection.execute("ROLLBACK")
                    return False
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def list_deliverables(self, work_item_id: UUID) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM deliverables WHERE work_item_id=? ORDER BY created_at,id", (str(work_item_id),)).fetchall()
        return tuple({"id": row["id"], "work_item_id": row["work_item_id"], "role_key": row["role_key"], "content": row["content"], "provider": row["provider"], "model": row["model"], "cost_usd": float(row["cost_usd"]), "created_at": row["created_at"], "review_required": bool(row["review_required"])} for row in rows)

    def get_work_item(self, item_id: UUID) -> WorkItem | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM work_items WHERE id=?", (str(item_id),)
            ).fetchone()
        if row is None:
            return None
        return WorkItem(
            id=UUID(row["id"]), title=row["title"], objective=row["objective"],
            department=row["department"], state=TaskState(row["state"]),
            assigned_agent_id=UUID(row["assigned_agent_id"]) if row["assigned_agent_id"] else None,
            depends_on=tuple(UUID(value) for value in json.loads(row["dependencies_json"])),
            created_at=datetime.fromisoformat(row["created_at"]),
            business_id=row["business_id"] if "business_id" in row.keys() else "core",
        )

    def list_work_items(
        self, *, state: TaskState | None = None, business_id: str | None = None,
        limit: int = 100,
    ) -> tuple[WorkItem, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        clauses, values = [], []
        if state is not None:
            clauses.append("state=?")
            values.append(state.value)
        if business_id is not None:
            from .domain import BUSINESS_UNIT_IDS
            if business_id not in BUSINESS_UNIT_IDS:
                raise ValueError(f"unknown business unit: {business_id}")
            clauses.append("business_id=?")
            values.append(business_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT id FROM work_items{where} ORDER BY created_at,id LIMIT ?",
                tuple(values),
            ).fetchall()
        return tuple(self.get_work_item(UUID(row["id"])) for row in rows)
