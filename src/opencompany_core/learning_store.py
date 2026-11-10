"""Durable evidence evaluations and owner-controlled improvement proposals."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from .domain import AuditRecord, TaskState
from .learning import ImprovementProposal, OutcomeEvaluation, ProposalState
from .persistence import _ZERO_HASH, _audit_payload, _digest, _json


class LearningRepository:
    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db = connection
        self._lock = lock
        with self._lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS outcome_evaluations (
                    id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL REFERENCES work_items(id),
                    evaluator TEXT NOT NULL,
                    grade TEXT NOT NULL,
                    rubric_scores_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    observations TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_evaluations_work_item ON outcome_evaluations(work_item_id,evaluated_at)"
            )
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS improvement_proposals (
                    id TEXT PRIMARY KEY,
                    target TEXT NOT NULL,
                    change_summary TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    expected_measurement TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    based_on_evaluations_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    owner_decision TEXT
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_improvement_state ON improvement_proposals(state,created_at)"
            )
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS approved_learning_notes (
                    id TEXT PRIMARY KEY,
                    role_key TEXT NOT NULL,
                    note TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    state TEXT NOT NULL
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_learning_notes_role ON approved_learning_notes(role_key,state,created_at)"
            )

    @staticmethod
    def _audit(record: AuditRecord, db: sqlite3.Connection) -> None:
        row = db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = row["event_hash"] if row else _ZERO_HASH
        payload = _audit_payload(record, previous)
        db.execute(
            "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
            (str(record.id), record.occurred_at.isoformat(), _json(payload), previous, _digest(payload)),
        )

    def save_evaluation(self, item: OutcomeEvaluation, record: AuditRecord) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                task = self._db.execute(
                    "SELECT state FROM work_items WHERE id=?", (str(item.work_item_id),)
                ).fetchone()
                if task is None or task["state"] not in {TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.READY.value}:
                    raise ValueError("outcome evaluations require a completed, failed, or owner-returned task")
                if task["state"] == TaskState.READY.value and not any(ref.startswith("deliverable:") for ref in item.evidence_refs):
                    raise ValueError("returned work evaluations must cite at least one deliverable")
                for ref in item.evidence_refs:
                    if ref.startswith("deliverable:"):
                        deliverable_id = ref.split(":", 1)[1]
                        row = self._db.execute(
                            "SELECT work_item_id FROM deliverables WHERE id=?", (deliverable_id,)
                        ).fetchone()
                        if row is None or row["work_item_id"] != str(item.work_item_id):
                            raise ValueError("evaluation evidence must reference deliverables from this work item")
                self._db.execute(
                    """INSERT INTO outcome_evaluations
                       (id,work_item_id,evaluator,grade,rubric_scores_json,evidence_refs_json,observations,evaluated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (str(item.id), str(item.work_item_id), item.evaluator, item.grade.value,
                     _json(dict(item.rubric_scores)), _json(list(item.evidence_refs)),
                     item.observations, item.evaluated_at.isoformat()),
                )
                self._audit(record, self._db)
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def list_evaluations(self, work_item_id: UUID | None = None) -> list[dict]:
        with self._lock:
            if work_item_id is None:
                rows = self._db.execute(
                    "SELECT * FROM outcome_evaluations ORDER BY evaluated_at DESC,id LIMIT 500"
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM outcome_evaluations WHERE work_item_id=? ORDER BY evaluated_at DESC,id",
                    (str(work_item_id),),
                ).fetchall()
        return [{
            "id": row["id"], "work_item_id": row["work_item_id"],
            "evaluator": row["evaluator"], "grade": row["grade"],
            "rubric_scores": json.loads(row["rubric_scores_json"]),
            "evidence_refs": json.loads(row["evidence_refs_json"]),
            "observations": row["observations"], "evaluated_at": row["evaluated_at"],
        } for row in rows]

    def save_proposal(self, item: ImprovementProposal, record: AuditRecord) -> None:
        if item.state != ProposalState.PROPOSED:
            raise ValueError("new improvement proposals must start in proposed state")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for evaluation_id in item.based_on_evaluations:
                    if self._db.execute(
                        "SELECT 1 FROM outcome_evaluations WHERE id=?", (str(evaluation_id),)
                    ).fetchone() is None:
                        raise ValueError("improvement proposal references an unknown evaluation")
                self._db.execute(
                    """INSERT INTO improvement_proposals
                       (id,target,change_summary,rationale,expected_measurement,risk_level,
                        based_on_evaluations_json,state,created_at,owner_decision)
                       VALUES(?,?,?,?,?,?,?,?,?,NULL)""",
                    (str(item.id), item.target, item.change_summary, item.rationale,
                     item.expected_measurement, item.risk_level,
                     _json([str(value) for value in item.based_on_evaluations]),
                     item.state.value, item.created_at.isoformat()),
                )
                self._audit(record, self._db)
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def list_proposals(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM improvement_proposals ORDER BY created_at DESC,id LIMIT 500"
            ).fetchall()
        return [{
            "id": row["id"], "target": row["target"],
            "change_summary": row["change_summary"], "rationale": row["rationale"],
            "expected_measurement": row["expected_measurement"], "risk_level": row["risk_level"],
            "based_on_evaluations": json.loads(row["based_on_evaluations_json"]),
            "state": row["state"], "created_at": row["created_at"],
            "owner_decision": row["owner_decision"],
        } for row in rows]

    def decide_proposal(
        self, proposal_id: UUID, *, approved: bool, owner_id: str,
        rationale: str, record: AuditRecord,
    ) -> bool:
        state = ProposalState.APPROVED.value if approved else ProposalState.REJECTED.value
        decision = f"{owner_id}: {rationale}"
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._db.execute(
                    """UPDATE improvement_proposals SET state=?,owner_decision=?
                       WHERE id=? AND state=?""",
                    (state, decision, str(proposal_id), ProposalState.PROPOSED.value),
                )
                if cursor.rowcount != 1:
                    self._db.execute("ROLLBACK")
                    return False
                self._audit(record, self._db)
                self._db.execute("COMMIT")
                return True
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def save_learning_note(
        self, *, role_key: str, note: str, evidence_refs: tuple[str, ...],
        owner_id: str, record: AuditRecord,
    ) -> str:
        if not role_key.strip() or not note.strip() or not evidence_refs:
            raise ValueError("learning notes require role, content and evidence")
        note_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for ref in evidence_refs:
                    if ref.startswith("evaluation:"):
                        found = self._db.execute(
                            "SELECT 1 FROM outcome_evaluations WHERE id=?", (ref.split(":",1)[1],)
                        ).fetchone()
                        if found is None:
                            raise ValueError("learning note references an unknown evaluation")
                self._db.execute(
                    """INSERT INTO approved_learning_notes
                       (id,role_key,note,evidence_refs_json,created_at,owner_id,state)
                       VALUES(?,?,?,?,?,?,'approved')""",
                    (note_id, role_key, note, _json(list(evidence_refs)), now, owner_id),
                )
                self._audit(record, self._db)
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        return note_id

    def list_learning_notes(self, role_key: str, *, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM approved_learning_notes WHERE role_key=? AND state='approved'
                   ORDER BY created_at DESC,id LIMIT ?""",
                (role_key, max(1, min(limit, 100))),
            ).fetchall()
        return [{
            "id": row["id"], "role_key": row["role_key"], "note": row["note"],
            "evidence_refs": json.loads(row["evidence_refs_json"]),
            "created_at": row["created_at"], "owner_id": row["owner_id"],
        } for row in rows]
