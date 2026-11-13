"""Business-scoped, approval-gated Product & R&D workflow persistence."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from .domain import AuditRecord
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json

PRODUCT_STAGES = (
    "opportunity_brief", "product_specification", "production_plan",
    "artifact_generation", "automated_qa", "human_preview",
    "packaging", "listing_packet", "ceo_review",
)
COMMERCIAL_UNITS = frozenset({"physical-agency", "physical-brand", "digital-products"})


class ProductRDError(ValueError):
    """Invalid product workflow state, scope, or transition."""


class ProductRDRepository:
    """SQLite workflow repository sharing the OpenCompany store lock and audit chain."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._db, self._lock = connection, lock
        with self._lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS product_rd_workflows (
                    id TEXT PRIMARY KEY,
                    business_id TEXT NOT NULL CHECK(business_id IN
                        ('physical-agency','physical-brand','digital-products')),
                    title TEXT NOT NULL,
                    brief TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stages_json TEXT NOT NULL,
                    cost_ceiling_usd REAL NOT NULL CHECK(cost_ceiling_usd = 0),
                    external_actions_enabled INTEGER NOT NULL CHECK(external_actions_enabled = 0),
                    owner_decision TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_rd_business_updated "
                "ON product_rd_workflows(business_id,updated_at)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "business_id": row["business_id"],
            "title": row["title"], "brief": row["brief"],
            "status": row["status"], "stages": json.loads(row["stages_json"]),
            "cost_ceiling_usd": float(row["cost_ceiling_usd"]),
            "external_actions_enabled": bool(row["external_actions_enabled"]),
            "owner_decision": row["owner_decision"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def _commit(self, workflow_id: str, workflow: dict[str, Any], *, action: str,
                actor_type: str, actor_id: str, details: dict[str, Any]) -> None:
        now = self._now()
        workflow["updated_at"] = now
        record = AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type=actor_type, actor_id=actor_id, action=action,
            subject_type="product_rd_workflow", subject_id=workflow_id,
            outcome=workflow["status"], correlation_id=workflow_id,
            details={"business_id": workflow["business_id"], **details},
        )
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    """UPDATE product_rd_workflows
                       SET status=?,stages_json=?,owner_decision=?,updated_at=?
                       WHERE id=? AND business_id=?""",
                    (workflow["status"], _json(workflow["stages"]),
                     workflow["owner_decision"], now, workflow_id, workflow["business_id"]),
                )
                previous = self._db.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                self._db.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, _digest(payload)),
                )
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def create(self, *, title: str, brief: str, business_id: str = "digital-products",
               actor_id: str = "owner") -> dict[str, Any]:
        title, brief = title.strip(), brief.strip()
        if business_id not in COMMERCIAL_UNITS:
            raise ProductRDError("Product work must belong to one commercial business unit.")
        if not title or len(title) > 240 or not brief or len(brief) > 12000:
            raise ProductRDError("Title and brief are required (maximum 240 and 12000 characters).")
        now, workflow_id = self._now(), str(uuid4())
        stages = []
        for index, key in enumerate(PRODUCT_STAGES):
            stages.append({
                "key": key,
                "status": "in_progress" if index == 0 else "pending",
                "owner_role": {
                    "opportunity_brief": "market_intelligence_analyst",
                    "product_specification": "product_planning_lead",
                    "production_plan": "product_planning_lead",
                    "artifact_generation": "deterministic_product_generator",
                    "automated_qa": "automated_quality_gate",
                    "human_preview": "owner_visual_reviewer",
                    "packaging": "product_planning_lead",
                    "listing_packet": "marketplace_operations_analyst",
                    "ceo_review": "chief_executive_orchestrator",
                }[key],
                "input": {"title": title, "brief": brief} if index == 0 else {},
                "output": None, "artifact_refs": [],
                "started_at": now if index == 0 else None,
                "completed_at": None, "cost_estimate_usd": 0.0, "cost_actual_usd": 0.0,
                "evidence": [], "blockers": [],
            })
        workflow = {
            "id": workflow_id, "business_id": business_id, "title": title,
            "brief": brief, "status": "in_progress", "stages": stages,
            "cost_ceiling_usd": 0.0, "external_actions_enabled": False,
            "owner_decision": None, "created_at": now, "updated_at": now,
        }
        record = AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id=actor_id, action="product_rd.created",
            subject_type="product_rd_workflow", subject_id=workflow_id,
            outcome="in_progress", correlation_id=workflow_id,
            details={"business_id": business_id, "cost_ceiling_usd": 0.0,
                     "external_actions_enabled": False},
        )
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    """INSERT INTO product_rd_workflows
                       (id,business_id,title,brief,status,stages_json,cost_ceiling_usd,
                        external_actions_enabled,owner_decision,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,0,0,NULL,?,?)""",
                    (workflow_id,business_id,title,brief,"in_progress",_json(stages),now,now),
                )
                previous = self._db.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                self._db.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id),record.occurred_at.isoformat(),_json(payload),
                     previous_hash,_digest(payload)),
                )
                self._db.execute("COMMIT")
            except Exception:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        return workflow

    def get(self, workflow_id: UUID | str, *, business_id: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM product_rd_workflows WHERE id=?"
        values: list[Any] = [str(workflow_id)]
        if business_id is not None:
            sql += " AND business_id=?"
            values.append(business_id)
        with self._lock:
            row = self._db.execute(sql, tuple(values)).fetchone()
        return self._decode(row) if row else None

    def list(self, *, business_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ProductRDError("limit must be between 1 and 100.")
        if business_id is not None and business_id not in COMMERCIAL_UNITS:
            raise ProductRDError("Unknown commercial business unit.")
        sql, values = "SELECT * FROM product_rd_workflows", []
        if business_id is not None:
            sql += " WHERE business_id=?"
            values.append(business_id)
        sql += " ORDER BY created_at DESC,id DESC LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._db.execute(sql, tuple(values)).fetchall()
        return [self._decode(row) for row in rows]

    def _load(self, workflow_id: UUID | str) -> dict[str, Any]:
        workflow = self.get(workflow_id)
        if workflow is None:
            raise ProductRDError("Product workflow not found.")
        return workflow

    def attach_work_item(self, workflow_id: UUID | str, stage_key: str, work_item_id: str,
                         *, actor_id: str = "owner", actor_type: str = "owner") -> dict[str, Any]:
        workflow = self._load(workflow_id)
        stage = next((s for s in workflow["stages"] if s["key"] == stage_key), None)
        if stage is None or stage["status"] != "in_progress":
            raise ProductRDError("A work item can only be attached to the active stage.")
        if stage.get("work_item_id"):
            raise ProductRDError("The active stage already has an assigned work item.")
        stage["work_item_id"] = work_item_id
        self._commit(str(workflow_id), workflow, action="product_rd.stage_work_item_attached",
                     actor_type=actor_type, actor_id=actor_id,
                     details={"stage": stage_key, "work_item_id": work_item_id})
        return self._load(workflow_id)

    def start_stage(self, workflow_id: UUID | str, stage_key: str, *, actor_id: str = "owner") -> dict[str, Any]:
        workflow = self._load(workflow_id)
        index = next((i for i, s in enumerate(workflow["stages"]) if s["key"] == stage_key), -1)
        if index < 0:
            raise ProductRDError("Unknown product stage.")
        stage = workflow["stages"][index]
        if stage["status"] != "pending" or any(
            s["status"] != "completed" for s in workflow["stages"][:index]
        ):
            raise ProductRDError("Only the next pending stage can be started.")
        stage["status"], stage["started_at"] = "in_progress", self._now()
        self._commit(str(workflow_id), workflow, action="product_rd.stage_started",
                     actor_type="owner", actor_id=actor_id, details={"stage": stage_key})
        return self._load(workflow_id)

    def complete_stage(self, workflow_id: UUID | str, stage_key: str, *, output: str,
                       evidence: list[str], artifact_refs: list[str] | None = None,
                       qa_result: dict[str, Any] | None = None,
                       cost_actual_usd: float = 0.0,
                       actor_id: str = "owner",
                       actor_type: str = "owner") -> dict[str, Any]:
        workflow = self._load(workflow_id)
        stage = next((s for s in workflow["stages"] if s["key"] == stage_key), None)
        if stage is None or stage["status"] != "in_progress":
            raise ProductRDError("Only the active stage can be completed.")
        if not output.strip() or len(output) > 12000:
            raise ProductRDError("Stage output is required (maximum 12000 characters).")
        try:
            actual_cost = float(cost_actual_usd)
        except (TypeError, ValueError) as exc:
            raise ProductRDError("Actual stage cost must be a finite USD amount.") from exc
        if not math.isfinite(actual_cost) or actual_cost < 0:
            raise ProductRDError("Actual stage cost must be a finite non-negative USD amount.")
        if actual_cost > 0:
            raise ProductRDError("Non-zero stage cost is blocked by the USD 0 product workflow ceiling.")
        if not evidence or len(evidence) > 30 or any(not isinstance(x,str) or not x.strip() for x in evidence):
            raise ProductRDError("Completion requires 1-30 evidence entries.")
        refs = artifact_refs or []
        if not refs:
            raise ProductRDError("A stage cannot complete without at least one persisted artifact reference.")
        if len(refs) > 30 or any(not isinstance(x,str) or not x.strip() or len(x)>500 for x in refs):
            raise ProductRDError("Artifact references must contain at most 30 non-empty entries.")
        if stage_key == "automated_qa":
            required = {"passed_checks","failed_checks","untested_claims"}
            if not isinstance(qa_result,dict) or set(qa_result) != required or any(
                not isinstance(qa_result[k],list) or len(qa_result[k]) > 30
                or any(not isinstance(value,str) or not value.strip() for value in qa_result[k])
                for k in required
            ):
                raise ProductRDError("QA requires bounded lists of non-empty strings for passed_checks, failed_checks, and untested_claims.")
            if not qa_result["passed_checks"] and not qa_result["failed_checks"]:
                raise ProductRDError("Automated QA must report at least one executed check.")
            if qa_result["failed_checks"]:
                stage["status"] = "blocked"
                workflow["status"] = "blocked"
                stage["blockers"] = [str(x)[:1000] for x in qa_result["failed_checks"]]
                stage["output"] = output
                stage["evidence"] = evidence
                stage["artifact_refs"] = refs
                stage["cost_actual_usd"] = actual_cost
                stage["qa_result"] = qa_result
                self._commit(str(workflow_id),workflow,action="product_rd.qa_failed",
                             actor_type=actor_type,actor_id=actor_id,details={"stage":stage_key,"qa_result":qa_result,"cost_actual_usd":actual_cost})
                return self._load(workflow_id)
            stage["qa_result"] = qa_result
        stage["status"], stage["output"] = "completed", output
        stage["artifact_refs"], stage["evidence"] = refs, evidence
        stage["cost_actual_usd"] = actual_cost
        stage["completed_at"] = self._now()
        index = PRODUCT_STAGES.index(stage_key)
        if index == len(PRODUCT_STAGES)-1:
            workflow["status"] = "awaiting_owner_review"
        else:
            next_stage = workflow["stages"][index+1]
            next_stage["status"], next_stage["started_at"] = "in_progress", self._now()
        self._commit(str(workflow_id),workflow,action="product_rd.stage_completed",
                     actor_type=actor_type,actor_id=actor_id,
                     details={"stage":stage_key,"artifact_refs":refs,"cost_actual_usd":actual_cost})
        return self._load(workflow_id)

    def return_to_production(self, workflow_id: UUID | str, *, rationale: str,
                             actor_id: str = "owner") -> dict[str, Any]:
        workflow = self._load(workflow_id)
        qa_index = PRODUCT_STAGES.index("automated_qa")
        qa = workflow["stages"][qa_index]
        if qa["status"] != "blocked" or not rationale.strip():
            raise ProductRDError("Only failed QA can be returned to production with a rationale.")
        for stage in workflow["stages"][PRODUCT_STAGES.index("artifact_generation"):]:
            stage.update(status="pending", output=None, artifact_refs=[], evidence=[],
                         blockers=[], started_at=None, completed_at=None,
                         qa_result=None, work_item_id=None, cost_actual_usd=0.0)
        production = workflow["stages"][PRODUCT_STAGES.index("artifact_generation")]
        production["status"], production["started_at"] = "in_progress", self._now()
        qa["rework_history"] = qa.get("rework_history", []) + [{"rationale":rationale[:2000],"returned_at":self._now()}]
        workflow["status"] = "in_progress"
        self._commit(str(workflow_id),workflow,action="product_rd.returned_to_production",
                     actor_type="owner",actor_id=actor_id,details={"rationale":rationale[:2000]})
        return self._load(workflow_id)

    def owner_review(self, workflow_id: UUID | str, *, approved: bool, rationale: str,
                     actor_id: str = "owner") -> dict[str, Any]:
        workflow = self._load(workflow_id)
        if workflow["status"] != "awaiting_owner_review" or not rationale.strip():
            raise ProductRDError("Owner review is available only after all stages are complete.")
        workflow["owner_decision"] = "approved_internal" if approved else "rejected_internal"
        workflow["status"] = workflow["owner_decision"]
        self._commit(str(workflow_id),workflow,action="product_rd.owner_reviewed",
                     actor_type="owner",actor_id=actor_id,details={"approved":approved,"rationale":rationale[:2000]})
        return self._load(workflow_id)
