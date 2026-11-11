"""Persisted, approval-gated Product & R&D workflow.

This module records internal production stages and evidence. It does not call
paid providers, publish listings, contact customers, or spend money.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import UUID, uuid4


STAGES = (
    "opportunity_brief",
    "product_specification",
    "production_plan",
    "artifact_generation",
    "automated_qa",
    "human_preview",
    "packaging",
    "listing_packet",
    "ceo_review",
)


class ProductWorkflowError(ValueError):
    pass


class ProductWorkflowRepository:
    """SQLite-backed product jobs sharing the core store transaction lock."""

    def __init__(self, connection: sqlite3.Connection, lock: RLock) -> None:
        self._connection = connection
        self._lock = lock
        with self._lock:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS product_workflows (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    brief TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stages_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cost_ceiling_usd REAL NOT NULL CHECK(cost_ceiling_usd = 0),
                    external_actions_enabled INTEGER NOT NULL CHECK(external_actions_enabled = 0),
                    owner_decision TEXT
                )
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "brief": row["brief"],
            "status": row["status"],
            "stages": json.loads(row["stages_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "cost_ceiling_usd": float(row["cost_ceiling_usd"]),
            "external_actions_enabled": bool(row["external_actions_enabled"]),
            "owner_decision": row["owner_decision"],
        }

    def create(self, title: str, brief: str) -> dict[str, Any]:
        title, brief = title.strip(), brief.strip()
        if not title or len(title) > 240 or not brief or len(brief) > 12000:
            raise ProductWorkflowError("A title and a 1-12000 character brief are required.")
        now = self._now()
        stages = [
            {
                "key": key,
                "status": "in_progress" if index == 0 else "pending",
                "owner_role": "product-rd-manager" if index in (0, 1, 2, 3, 4, 5, 6, 7) else "chief-executive-orchestrator",
                "input": {"product_title": title, "brief": brief} if index == 0 else {},
                "output": None,
                "artifact_refs": [],
                "started_at": now if index == 0 else None,
                "completed_at": None,
                "cost_estimate_usd": 0.0,
                "evidence": [],
                "blockers": [],
            }
            for index, key in enumerate(STAGES)
        ]
        workflow_id = str(uuid4())
        with self._lock:
            self._connection.execute(
                """INSERT INTO product_workflows
                   (id,title,brief,status,stages_json,created_at,updated_at,
                    cost_ceiling_usd,external_actions_enabled,owner_decision)
                   VALUES(?,?,?,?,?,?,?,?,?,NULL)""",
                (workflow_id, title, brief, "in_progress",
                 json.dumps(stages, sort_keys=True), now, now, 0.0, 0),
            )
            row = self._connection.execute(
                "SELECT * FROM product_workflows WHERE id=?", (workflow_id,)
            ).fetchone()
        return self._decode(row)

    def get(self, workflow_id: UUID | str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM product_workflows WHERE id=?", (str(workflow_id),)
            ).fetchone()
        return self._decode(row) if row else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ProductWorkflowError("limit must be between 1 and 100.")
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM product_workflows ORDER BY created_at DESC,id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def start_stage(self, workflow_id: UUID | str, stage_key: str) -> dict[str, Any]:
        return self._mutate_stage(workflow_id, stage_key, "start")

    def complete_stage(
        self, workflow_id: UUID | str, stage_key: str, *,
        output: str, artifact_refs: list[str], evidence: list[str],
        qa_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not output.strip() or len(output) > 12000:
            raise ProductWorkflowError("Stage output must contain 1-12000 characters.")
        if len(artifact_refs) > 30 or any(not ref.strip() or len(ref) > 500 for ref in artifact_refs):
            raise ProductWorkflowError("Artifact references must be non-empty and limited to 30.")
        if len(evidence) > 30 or any(not item.strip() or len(item) > 1000 for item in evidence):
            raise ProductWorkflowError("Evidence entries must be non-empty and limited to 30.")
        if stage_key == "automated_qa":
            required = {"passed_checks", "failed_checks", "untested_claims"}
            if not isinstance(qa_result, dict) or set(qa_result) != required:
                raise ProductWorkflowError("Automated QA requires passed_checks, failed_checks, and untested_claims.")
            if any(not isinstance(qa_result[key], list) for key in required):
                raise ProductWorkflowError("Automated QA result fields must be lists.")
            if any(not isinstance(item, str) or not item.strip() for key in required for item in qa_result[key]):
                raise ProductWorkflowError("Automated QA entries must be non-empty strings.")
        return self._mutate_stage(
            workflow_id, stage_key, "complete",
            output=output, artifact_refs=artifact_refs, evidence=evidence,
            qa_result=qa_result,
        )

    def block_stage(self, workflow_id: UUID | str, stage_key: str, reason: str) -> dict[str, Any]:
        if not reason.strip() or len(reason) > 2000:
            raise ProductWorkflowError("A blocker reason of 1-2000 characters is required.")
        return self._mutate_stage(workflow_id, stage_key, "block", reason=reason)

    def _mutate_stage(self, workflow_id: UUID | str, stage_key: str, action: str, **values: Any) -> dict[str, Any]:
        if stage_key not in STAGES:
            raise ProductWorkflowError("Unknown product workflow stage.")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM product_workflows WHERE id=?", (str(workflow_id),)
                ).fetchone()
                if row is None:
                    raise ProductWorkflowError("Product workflow not found.")
                record = self._decode(row)
                if record["status"] in {"awaiting_owner_review", "approved", "rejected"}:
                    raise ProductWorkflowError("This product workflow is already awaiting or has received owner review.")
                stages = record["stages"]
                index = STAGES.index(stage_key)
                stage = stages[index]
                if action == "start":
                    if stage["status"] != "pending":
                        raise ProductWorkflowError("Only a pending stage can be started.")
                    if index and stages[index - 1]["status"] != "completed":
                        raise ProductWorkflowError("The preceding stage must be completed first.")
                    stage["status"] = "in_progress"
                    stage["started_at"] = self._now()
                elif action == "complete":
                    if stage["status"] != "in_progress":
                        raise ProductWorkflowError("Only an in-progress stage can be completed.")
                    stage["status"] = "completed"
                    stage["output"] = values["output"]
                    stage["artifact_refs"] = values["artifact_refs"]
                    stage["evidence"] = values["evidence"]
                    if stage_key == "automated_qa":
                        stage["qa_result"] = values["qa_result"]
                    stage["completed_at"] = self._now()
                elif action == "block":
                    if stage["status"] not in {"pending", "in_progress"}:
                        raise ProductWorkflowError("Only pending or active stages can be blocked.")
                    stage["status"] = "blocked"
                    stage["blockers"].append(values["reason"])
                if all(item["status"] == "completed" for item in stages[:-1]):
                    final = stages[-1]
                    if final["status"] == "pending":
                        final["status"] = "in_progress"
                        final["started_at"] = self._now()
                    status = "awaiting_owner_review" if final["status"] == "completed" else "in_progress"
                else:
                    status = "blocked" if any(item["status"] == "blocked" for item in stages) else "in_progress"
                now = self._now()
                self._connection.execute(
                    "UPDATE product_workflows SET stages_json=?,status=?,updated_at=? WHERE id=?",
                    (json.dumps(stages, sort_keys=True), status, now, str(workflow_id)),
                )
                updated = self._connection.execute(
                    "SELECT * FROM product_workflows WHERE id=?", (str(workflow_id),)
                ).fetchone()
                self._connection.execute("COMMIT")
                return self._decode(updated)
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise


    def return_to_production(self, workflow_id: UUID | str, reason: str) -> dict[str, Any]:
        """Return a blocked QA result to artifact production and reset downstream stages."""
        if not reason.strip() or len(reason) > 2000:
            raise ProductWorkflowError("A rework reason of 1-2000 characters is required.")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM product_workflows WHERE id=?", (str(workflow_id),)
                ).fetchone()
                if row is None:
                    raise ProductWorkflowError("Product workflow not found.")
                record = self._decode(row)
                if record["status"] != "blocked" or record["stages"][4]["status"] != "blocked":
                    raise ProductWorkflowError("Only a blocked automated QA stage can be returned to production.")
                stages = record["stages"]
                for index in range(3, len(stages)):
                    stage = stages[index]
                    stage["status"] = "pending"
                    stage["started_at"] = None
                    stage["completed_at"] = None
                    stage["output"] = None
                    stage["artifact_refs"] = []
                    stage["evidence"] = []
                    stage.pop("qa_result", None)
                production = stages[3]
                production["status"] = "in_progress"
                production["started_at"] = self._now()
                production["blockers"].append("QA rework: " + reason)
                now = self._now()
                self._connection.execute(
                    "UPDATE product_workflows SET stages_json=?,status='in_progress',updated_at=? WHERE id=?",
                    (json.dumps(stages, sort_keys=True), now, str(workflow_id)),
                )
                updated = self._connection.execute(
                    "SELECT * FROM product_workflows WHERE id=?", (str(workflow_id),)
                ).fetchone()
                self._connection.execute("COMMIT")
                return self._decode(updated)
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def owner_review(self, workflow_id: UUID | str, *, approved: bool, rationale: str) -> dict[str, Any]:
        if not rationale.strip() or len(rationale) > 2000:
            raise ProductWorkflowError("A review rationale of 1-2000 characters is required.")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM product_workflows WHERE id=?", (str(workflow_id),)
                ).fetchone()
                if row is None:
                    raise ProductWorkflowError("Product workflow not found.")
                record = self._decode(row)
                if record["status"] != "awaiting_owner_review":
                    raise ProductWorkflowError("The product workflow is not ready for owner review.")
                stages = record["stages"]
                final = stages[-1]
                final["status"] = "completed" if approved else "rejected"
                final["output"] = rationale
                final["evidence"] = ["owner_review_decision"]
                final["completed_at"] = self._now()
                status = "approved_internal" if approved else "rejected"
                self._connection.execute(
                    "UPDATE product_workflows SET stages_json=?,status=?,updated_at=?,owner_decision=? WHERE id=?",
                    (json.dumps(stages, sort_keys=True), status, self._now(),
                     "approved" if approved else "rejected", str(workflow_id)),
                )
                updated = self._connection.execute(
                    "SELECT * FROM product_workflows WHERE id=?", (str(workflow_id),)
                ).fetchone()
                self._connection.execute("COMMIT")
                return self._decode(updated)
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
