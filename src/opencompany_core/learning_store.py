"""Durable evidence evaluations and owner-controlled improvement proposals."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from .domain import BUSINESS_UNIT_IDS, AuditRecord, TaskState
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
                    owner_decision TEXT,
                    business_id TEXT NOT NULL DEFAULT 'core'
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
                    state TEXT NOT NULL,
                    business_id TEXT NOT NULL DEFAULT 'core'
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_learning_notes_role ON approved_learning_notes(role_key,state,created_at)"
            )
            for table in ("improvement_proposals", "approved_learning_notes"):
                columns = {
                    row["name"] for row in self._db.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                }
                if "business_id" not in columns:
                    self._db.execute(
                        f"ALTER TABLE {table} ADD COLUMN business_id TEXT NOT NULL DEFAULT 'core'"
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
                    """SELECT e.*,w.business_id FROM outcome_evaluations e
                       JOIN work_items w ON w.id=e.work_item_id
                       ORDER BY e.evaluated_at DESC,e.id LIMIT 500"""
                ).fetchall()
            else:
                rows = self._db.execute(
                    """SELECT e.*,w.business_id FROM outcome_evaluations e
                       JOIN work_items w ON w.id=e.work_item_id
                       WHERE e.work_item_id=? ORDER BY e.evaluated_at DESC,e.id""",
                    (str(work_item_id),),
                ).fetchall()
        return [{
            "id": row["id"], "work_item_id": row["work_item_id"],
            "business_id": row["business_id"],
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
                placeholders = ",".join("?" for _ in item.based_on_evaluations)
                business_rows = self._db.execute(
                    f"""SELECT e.id,w.business_id FROM outcome_evaluations e
                        JOIN work_items w ON w.id=e.work_item_id
                        WHERE e.id IN ({placeholders})""",
                    tuple(str(value) for value in item.based_on_evaluations),
                ).fetchall()
                business_ids = {row["business_id"] for row in business_rows}
                if len(business_rows) != len(item.based_on_evaluations) or len(business_ids) != 1:
                    raise ValueError("improvement proposal evaluations must exist and belong to one business unit")
                business_id = next(iter(business_ids))
                self._db.execute(
                    """INSERT INTO improvement_proposals
                       (id,target,change_summary,rationale,expected_measurement,risk_level,
                        based_on_evaluations_json,state,created_at,owner_decision,business_id)
                       VALUES(?,?,?,?,?,?,?,?,?,NULL,?)""",
                    (str(item.id), item.target, item.change_summary, item.rationale,
                     item.expected_measurement, item.risk_level,
                     _json([str(value) for value in item.based_on_evaluations]),
                     item.state.value, item.created_at.isoformat(), business_id),
                )
                self._audit(record, self._db)
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def list_proposals(self, business_id: str | None = None) -> list[dict]:
        if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
            raise ValueError("unknown business unit for proposal lookup")
        with self._lock:
            if business_id is None:
                rows = self._db.execute(
                    "SELECT * FROM improvement_proposals ORDER BY created_at DESC,id LIMIT 500"
                ).fetchall()
            else:
                rows = self._db.execute(
                    """SELECT * FROM improvement_proposals WHERE business_id=?
                       ORDER BY created_at DESC,id LIMIT 500""",
                    (business_id,),
                ).fetchall()
        return [{
            "id": row["id"], "target": row["target"],
            "change_summary": row["change_summary"], "rationale": row["rationale"],
            "expected_measurement": row["expected_measurement"], "risk_level": row["risk_level"],
            "based_on_evaluations": json.loads(row["based_on_evaluations_json"]),
            "business_id": row["business_id"],
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
        owner_id: str, record: AuditRecord, business_id: str = "core",
    ) -> str:
        if not role_key.strip() or not note.strip() or not evidence_refs:
            raise ValueError("learning notes require role, content and evidence")
        if business_id not in BUSINESS_UNIT_IDS:
            raise ValueError("unknown business unit for learning note")
        note_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for ref in evidence_refs:
                    if ref.startswith("evaluation:"):
                        found = self._db.execute(
                            """SELECT w.business_id FROM outcome_evaluations e
                               JOIN work_items w ON w.id=e.work_item_id WHERE e.id=?""",
                            (ref.split(":",1)[1],),
                        ).fetchone()
                        if found is None or found["business_id"] != business_id:
                            raise ValueError("learning note evidence must belong to the selected business unit")
                    elif ref.startswith("deliverable:"):
                        found = self._db.execute(
                            """SELECT w.business_id FROM deliverables d
                               JOIN work_items w ON w.id=d.work_item_id WHERE d.id=?""",
                            (ref.split(":", 1)[1],),
                        ).fetchone()
                        if found is None or found["business_id"] != business_id:
                            raise ValueError("learning note deliverable evidence must belong to the selected business unit")
                self._db.execute(
                    """INSERT INTO approved_learning_notes
                       (id,role_key,note,evidence_refs_json,created_at,owner_id,state,business_id)
                       VALUES(?,?,?,?,?,?,'approved',?)""",
                    (note_id, role_key, note, _json(list(evidence_refs)), now, owner_id, business_id),
                )
                self._audit(record, self._db)
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        return note_id

    def apply_proposal_as_note(
        self, proposal_id: UUID, *, owner_id: str, record: AuditRecord
    ) -> str:
        """Apply an approved role-learning proposal as a durable prompt note atomically."""
        note_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                proposal = self._db.execute(
                    "SELECT * FROM improvement_proposals WHERE id=?", (str(proposal_id),)
                ).fetchone()
                if proposal is None or proposal["state"] != ProposalState.APPROVED.value:
                    raise ValueError("only owner-approved improvement proposals can become learning notes")
                role_key = proposal["target"]
                evidence_ids = json.loads(proposal["based_on_evaluations_json"])
                for evaluation_id in evidence_ids:
                    evaluation = self._db.execute(
                        """SELECT w.business_id FROM outcome_evaluations e
                           JOIN work_items w ON w.id=e.work_item_id WHERE e.id=?""",
                        (evaluation_id,),
                    ).fetchone()
                    if evaluation is None or evaluation["business_id"] != proposal["business_id"]:
                        raise ValueError("approved proposal evidence must remain inside its business unit")
                evidence_refs = [f"evaluation:{value}" for value in evidence_ids]
                self._db.execute(
                    """INSERT INTO approved_learning_notes
                       (id,role_key,note,evidence_refs_json,created_at,owner_id,state,business_id)
                       VALUES(?,?,?,?,?,?,'approved',?)""",
                    (note_id, role_key, proposal["change_summary"],
                     _json(evidence_refs), now, owner_id, proposal["business_id"]),
                )
                cursor = self._db.execute(
                    """UPDATE improvement_proposals SET state=?,owner_decision=?
                       WHERE id=? AND state=?""",
                    (ProposalState.IMPLEMENTED.value,
                     f"{proposal['owner_decision']} | applied as approved role-learning note",
                     str(proposal_id), ProposalState.APPROVED.value),
                )
                if cursor.rowcount != 1:
                    raise ValueError("proposal state changed while applying learning note")
                self._audit(record, self._db)
                self._db.execute("COMMIT")
                return note_id
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def list_learning_notes(
        self, role_key: str, business_id: str = "core", *, limit: int = 20
    ) -> list[dict]:
        if business_id not in BUSINESS_UNIT_IDS:
            raise ValueError("unknown business unit for learning-note lookup")
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM approved_learning_notes
                   WHERE role_key=? AND business_id=? AND state='approved'
                   ORDER BY created_at DESC,id LIMIT ?""",
                (role_key, business_id, max(1, min(limit, 100))),
            ).fetchall()
        return [{
            "id": row["id"], "role_key": row["role_key"], "note": row["note"],
            "business_id": row["business_id"],
            "evidence_refs": json.loads(row["evidence_refs_json"]),
            "created_at": row["created_at"], "owner_id": row["owner_id"],
        } for row in rows]
