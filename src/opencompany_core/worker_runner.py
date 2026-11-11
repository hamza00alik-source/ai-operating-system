"""Bounded queue-to-specialist worker orchestration.

Workers execute only explicitly assigned, in-progress work. They have no
external-action tools. Deliverables are handed to an injected artifact sink
and remain review-required; a missing sink fails closed.
"""
from __future__ import annotations

import math
import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5, uuid4

from .domain import AuditRecord, TaskState
from .execution import AgentDeliverable, AgentExecutor
from .persistence import SQLiteStore
from .worker_queue import DurableWorkerQueue, QueueError, WorkerLease
from .organization import default_organization
from .workforce import default_workforce, specialist_role_keys


class ArtifactSink(Protocol):
    def save(self, deliverable: AgentDeliverable) -> None:
        """Persist durably and idempotently using deliverable.id as the key."""


class WorkerConfigurationError(RuntimeError):
    pass


class OpenCompanyWorker:
    """Run one leased task per call; safe to supervise from a process loop."""

    def __init__(
        self,
        queue: DurableWorkerQueue,
        store: SQLiteStore,
        executor: AgentExecutor,
        artifact_sink: ArtifactSink | None,
        *,
        request_budget_usd: float = 0.0,
        preferred_provider: str | None = None,
        manager_review_callback: Callable[[UUID], object] | None = None,
    ) -> None:
        if artifact_sink is None:
            raise WorkerConfigurationError("a durable artifact sink is required")
        if not math.isfinite(request_budget_usd) or request_budget_usd < 0:
            raise ValueError("request budget must be a finite, non-negative amount")
        self.queue = queue
        self.store = store
        self.executor = executor
        self.artifact_sink = artifact_sink
        self.request_budget_usd = request_budget_usd
        self.preferred_provider = preferred_provider
        self.manager_review_callback = manager_review_callback

    def available_agent_ids(self) -> tuple[UUID, ...]:
        """Return only assignees with queued work or expired leases."""
        return self.queue.available_agent_ids()

    def run_once(self, agent_id: UUID, role_key: str) -> str:
        lease = self.queue.claim(agent_id)
        if lease is None:
            return "idle"
        try:
            existing_item = self.store.get_work_item(lease.work_item_id)
            if existing_item is not None and existing_item.state in {TaskState.REVIEW, TaskState.COMPLETED}:
                saved = self.store.list_deliverables(lease.work_item_id)
                if any(value["role_key"] == role_key for value in saved):
                    review_result = None
                    if existing_item.state == TaskState.REVIEW:
                        review_result = self._attempt_manager_review(lease, role_key)
                    return self._finish_after_manager_review(lease, role_key, review_result)
            deliverable = self._execute_lease(lease, role_key)
            # A retry of the same work/role must address the same artifact key.
            # This lets a durable sink safely deduplicate after a crash between
            # saving the artifact and acknowledging the queue lease.
            stable_id = uuid5(
                NAMESPACE_URL,
                f"opencompany:deliverable:{lease.work_item_id}:{role_key}",
            )
            deliverable = replace(deliverable, id=stable_id)
            self.artifact_sink.save(deliverable)
            saved = self.store.save_deliverable_with_audit(
                deliverable,
                self._audit(
                    lease, "worker.deliverable_saved",
                    {"role_key": role_key, "deliverable_id": str(deliverable.id),
                     "provider": deliverable.provider, "model": deliverable.model,
                     "cost_usd": deliverable.cost_usd, "review_required": True,
                     "task_state": "review"},
                ),
            )
            if not saved:
                raise WorkerConfigurationError("work item is no longer in progress")
            review_result = self._attempt_manager_review(lease, role_key)
            return self._finish_after_manager_review(lease, role_key, review_result)
        except Exception as exc:
            # Do not leak exception text into persistent queue metadata.
            queue_state = None
            try:
                queue_state = self.queue.fail(lease, type(exc).__name__[:120])
            except QueueError:
                pass
            failure_event = self._audit(
                lease, "worker.execution_failed",
                {"role_key": role_key, "error_type": type(exc).__name__, "queue_state": queue_state},
            )
            if queue_state == "dead":
                self.store.fail_work_item_with_audit(lease.work_item_id, failure_event)
            else:
                self.store.append_audit_record(failure_event)
            raise

    def _attempt_manager_review(self, lease: WorkerLease, role_key: str) -> object | None:
        """Run the internal quality gate when explicitly enabled; defer safely on failure."""
        enabled = os.environ.get("OPENCOMPANY_AUTO_MANAGER_REVIEW", "false").strip().casefold() in {"1", "true", "yes", "on"}
        if not enabled:
            return None
        item = self.store.get_work_item(lease.work_item_id)
        if item is None:
            return None
        department = default_organization().get(item.department)
        # Department managers and the CEO must remain subject to owner review;
        # this gate is only for specialist deliverables, never manager self-review.
        if role_key in {department.manager_role_key, "chief_executive_orchestrator"}:
            return None
        error_type = None
        try:
            if self.manager_review_callback is None:
                raise WorkerConfigurationError("manager review callback is not configured")
            return self.manager_review_callback(lease.work_item_id)
        except Exception as exc:
            error_type = type(exc).__name__
        self.store.append_audit_record(self._audit(
            lease, "manager.review_deferred",
            {"role_key": role_key, "error_type": error_type, "task_state": "review"},
        ))

    def _finish_after_manager_review(
        self, lease: WorkerLease, role_key: str, review_result: object | None,
    ) -> str:
        item = self.store.get_work_item(lease.work_item_id)
        if (
            item is not None and item.state == TaskState.READY
            and isinstance(review_result, dict)
            and review_result.get("auto_queue_enabled") is True
            and review_result.get("free_provider_ready") is True
        ):
            self.queue.requeue_after_manager_review(
                lease, item, lease.payload,
                self._audit(
                    lease, "manager.rework_auto_requeued",
                    {"role_key": role_key, "request_budget_usd": 0.0},
                ),
            )
            return "manager_rework_requeued"
        self.queue.complete(lease)
        if item and item.state == TaskState.COMPLETED:
            return "completed_manager_review"
        if item and item.state == TaskState.READY:
            return "manager_rework_requested"
        return "completed_review_required"

    def _execute_lease(self, lease: WorkerLease, role_key: str) -> AgentDeliverable:
        item = self.store.get_work_item(lease.work_item_id)
        if item is None:
            raise WorkerConfigurationError("queued work item does not exist")
        if item.assigned_agent_id != lease.agent_id:
            raise WorkerConfigurationError("queued agent does not match work-item assignment")
        if item.state != TaskState.IN_PROGRESS:
            raise WorkerConfigurationError("work item must be in progress before execution")
        agent = self.store.get_agent(lease.agent_id)
        if agent is None:
            raise WorkerConfigurationError("assigned agent profile does not exist")
        if agent.state.value != "active":
            raise WorkerConfigurationError("assigned agent profile is not active")
        if agent.department != item.department:
            raise WorkerConfigurationError("assigned agent department does not match work item")
        if agent.role_key != role_key:
            raise WorkerConfigurationError("execution role does not match assigned agent profile")
        try:
            department = default_organization().get(item.department)
        except LookupError as exc:
            raise WorkerConfigurationError("work item department is not registered") from exc
        if role_key not in department.role_keys:
            raise WorkerConfigurationError("execution role is not permitted in the work item department")
        if role_key in specialist_role_keys(item.department):
            expected_team = default_workforce().get(role_key).team_key
        elif role_key == "chief_executive_orchestrator":
            expected_team = "executive"
        else:
            expected_team = "management"
        if agent.team_key != expected_team:
            raise WorkerConfigurationError("assigned agent team does not match its workforce role")
        return self.executor.execute(
            role_key, item, request_budget_usd=self.request_budget_usd,
            preferred_provider=self.preferred_provider,
        )

    @staticmethod
    def _audit(lease: WorkerLease, action: str, details: dict) -> AuditRecord:
        return AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="agent", actor_id=str(lease.agent_id), action=action,
            subject_type="work_item", subject_id=str(lease.work_item_id),
            outcome="recorded" if action.endswith("saved") else "failed",
            correlation_id=str(lease.lease_token), details=details,
        )
