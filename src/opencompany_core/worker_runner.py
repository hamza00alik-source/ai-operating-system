"""Bounded queue-to-specialist worker orchestration.

Workers execute only explicitly assigned, in-progress work. They have no
external-action tools. Deliverables are handed to an injected artifact sink
and remain review-required; a missing sink fails closed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from .domain import AuditRecord, TaskState
from .execution import AgentDeliverable, AgentExecutor
from .model_gateway import ModelGateway
from .persistence import SQLiteStore
from .worker_queue import DurableWorkerQueue, QueueError, WorkerLease


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
    ) -> None:
        if artifact_sink is None:
            raise WorkerConfigurationError("a durable artifact sink is required")
        if request_budget_usd < 0:
            raise ValueError("request budget cannot be negative")
        self.queue = queue
        self.store = store
        self.executor = executor
        self.artifact_sink = artifact_sink
        self.request_budget_usd = request_budget_usd
        self.preferred_provider = preferred_provider

    def run_once(self, agent_id: UUID, role_key: str) -> str:
        lease = self.queue.claim(agent_id)
        if lease is None:
            return "idle"
        try:
            deliverable = self._execute_lease(lease, role_key)
            self.artifact_sink.save(deliverable)
            self.store.append_audit_record(self._audit(
                lease, "worker.deliverable_saved",
                {"role_key": role_key, "deliverable_id": str(deliverable.id),
                 "provider": deliverable.provider, "model": deliverable.model,
                 "cost_usd": deliverable.cost_usd, "review_required": True},
            ))
            self.queue.complete(lease)
            return "completed_review_required"
        except Exception as exc:
            # Do not leak exception text into persistent queue metadata.
            try:
                self.queue.fail(lease, type(exc).__name__[:120])
            except QueueError:
                pass
            self.store.append_audit_record(self._audit(
                lease, "worker.execution_failed",
                {"role_key": role_key, "error_type": type(exc).__name__},
            ))
            raise

    def _execute_lease(self, lease: WorkerLease, role_key: str) -> AgentDeliverable:
        item = self.store.get_work_item(lease.work_item_id)
        if item is None:
            raise WorkerConfigurationError("queued work item does not exist")
        if item.assigned_agent_id != lease.agent_id:
            raise WorkerConfigurationError("queued agent does not match work-item assignment")
        if item.state != TaskState.IN_PROGRESS:
            raise WorkerConfigurationError("work item must be in progress before execution")
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
