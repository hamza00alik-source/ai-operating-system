"""Bounded queue-to-specialist worker orchestration.

Workers execute only explicitly assigned, in-progress work. They have no
external-action tools. Deliverables are handed to an injected artifact sink
and remain review-required; a missing sink fails closed.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import replace
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Protocol, Callable
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
        approval_request_sink: Callable[[UUID, object, list[dict]], object] | None = None,
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
        self.approval_request_sink = approval_request_sink

    def available_agent_ids(self) -> tuple[UUID, ...]:
        """Return only assignees with queued work or expired leases."""
        return self.queue.available_agent_ids()

    def run_once(self, agent_id: UUID, role_key: str) -> str:
        lease = self.queue.claim(agent_id)
        if lease is None:
            return "idle"

        # Long model requests must not let their lease expire and be reclaimed
        # by another process. A failed heartbeat fences this worker from saving.
        heartbeat_stop = Event()
        lease_lost = Event()
        heartbeat_interval = max(0.1, min(60.0, self.queue.lease_seconds / 3))

        def keep_lease_alive() -> None:
            while not heartbeat_stop.wait(heartbeat_interval):
                try:
                    if not self.queue.renew(lease):
                        lease_lost.set()
                        return
                except Exception:
                    lease_lost.set()
                    return

        heartbeat = Thread(
            target=keep_lease_alive,
            name=f"opencompany-lease-{lease.work_item_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            existing_item = self.store.get_work_item(lease.work_item_id)
            if existing_item is not None and existing_item.state == TaskState.REVIEW:
                saved = self.store.list_deliverables(lease.work_item_id)
                if any(value["role_key"] == role_key for value in saved):
                    if lease_lost.is_set():
                        raise QueueError("worker lease was lost before queue acknowledgement")
                    self.queue.complete(lease)
                    return "completed_review_required"
            deliverable = self._execute_lease(lease, role_key)
            approval_requests, cleaned_content = self._extract_approval_requests(deliverable.content)
            if approval_requests and self.approval_request_sink is not None:
                if existing_item is None:
                    raise WorkerConfigurationError("approval request has no originating work item")
                self.approval_request_sink(lease.agent_id, existing_item, approval_requests)
                deliverable = replace(deliverable, content=cleaned_content)
            if lease_lost.is_set():
                raise QueueError("worker lease was lost during execution; result was not persisted")
            # A retry of the same work/role must address the same artifact key.
            # This lets a durable sink safely deduplicate after a crash between
            # saving the artifact and acknowledging the queue lease.
            stable_id = uuid5(
                NAMESPACE_URL,
                f"opencompany:deliverable:{lease.work_item_id}:{role_key}",
            )
            deliverable = replace(deliverable, id=stable_id)
            self.artifact_sink.save(deliverable)
            if lease_lost.is_set():
                raise QueueError("worker lease was lost before deliverable persistence")
            saved = self.store.save_deliverable_with_audit(
                deliverable,
                self._audit(
                    lease, "worker.deliverable_saved",
                    {"role_key": role_key, "deliverable_id": str(deliverable.id),
                     "provider": deliverable.provider, "model": deliverable.model,
                     "cost_usd": deliverable.cost_usd, "review_required": True,
                     "task_state": "review"},
                ),
                expected_agent_id=lease.agent_id,
            )
            if not saved:
                raise WorkerConfigurationError("work item is no longer in progress or worker authorization changed")
            if lease_lost.is_set():
                raise QueueError("worker lease was lost before queue acknowledgement")
            self.queue.complete(lease)
            return "completed_review_required"
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
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=max(1.0, heartbeat_interval * 2))

    @staticmethod
    def _extract_approval_requests(content: str) -> tuple[list[dict], str]:
        """Extract at most five allowlisted approval intents from one exact block."""
        pattern = re.compile(
            r"<OPENCOMPANY_APPROVAL_REQUESTS>(?:\\[nrt]|\s)*(\[.*?\])(?:\\[nrt]|\s)*</OPENCOMPANY_APPROVAL_REQUESTS>",
            re.DOTALL,
        )
        matches = list(pattern.finditer(content))
        if len(matches) != 1:
            return [], content
        try:
            decoded = json.loads(matches[0].group(1))
        except (TypeError, ValueError):
            return [], content
        if not isinstance(decoded, list) or not 1 <= len(decoded) <= 5:
            return [], content
        allowed = {
            "publish_listing", "send_customer_message", "make_customer_commitment",
            "purchase", "payment", "production_change", "credential_change",
            "account_change", "deploy_production", "delete_customer_data", "other",
        }
        accepted = []
        for value in decoded:
            if not isinstance(value, dict) or set(value) - {
                "action_type", "title", "description", "target_reference",
                "estimated_amount_minor", "currency",
            }:
                return [], content
            action = value.get("action_type")
            title = value.get("title")
            description = value.get("description")
            if (action not in allowed or not isinstance(title, str) or not title.strip()
                    or len(title) > 200 or not isinstance(description, str)
                    or not description.strip() or len(description) > 4000):
                return [], content
            target = value.get("target_reference")
            if target is not None and (not isinstance(target, str) or len(target) > 500):
                return [], content
            amount = value.get("estimated_amount_minor")
            currency = value.get("currency")
            if (amount is None) != (currency is None):
                return [], content
            if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int)
                                       or amount < 0 or amount > 9_000_000_000_000_000):
                return [], content
            if currency is not None and (not isinstance(currency, str)
                                         or not re.fullmatch(r"[A-Za-z]{3}", currency)):
                return [], content
            accepted.append({
                "action_type": action, "title": title.strip(),
                "description": description.strip(), "target_reference": target,
                "estimated_amount_minor": amount,
                "currency": currency.upper() if currency else None,
            })
        cleaned = (content[:matches[0].start()] + content[matches[0].end():]).strip()
        cleaned = re.sub(r"(?:\\[nrt])+$", "", cleaned).rstrip()
        if not cleaned:
            cleaned = "Draft deliverable contained only an external approval request; see owner approval inbox."
        return accepted, cleaned

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
