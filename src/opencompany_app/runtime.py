"""Composition root for the independent OpenCompany runtime.

The API and worker process share one SQLite database. Queue admission, queue
claim, task-state transitions, and audit events therefore use one transaction
boundary. Importing this module never starts a worker.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from opencompany_core.execution import AgentExecutor
from opencompany_core.model_gateway import ModelGateway
from opencompany_core.unorouter_adapter import UNOROUTER_AUTO_FREE_MODEL, configured_unorouter_gateway
from opencompany_core.persistence import SQLiteStore
from opencompany_core.worker_queue import DurableWorkerQueue
from opencompany_core.worker_runner import OpenCompanyWorker
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.owner_sessions import OwnerSessionStore
from opencompany_core.worker_fleet import WorkerFleet
from opencompany_core.collaboration_store import HandoffRepository
from opencompany_core.learning_store import LearningRepository
from opencompany_core.github_evolution import GitHubEvolutionClient
from opencompany_core.api_anything import ApiAnythingClient
from opencompany_core.research_broker import ResearchBroker
from opencompany_core.secret_vault import ProviderSecretVault, SecretVaultError
from opencompany_core.model_usage import ModelUsageRepository
from opencompany_core.domain import AgentState, AuditRecord, TaskState
from opencompany_core.manager_review import review_specialist_deliverables
from opencompany_core.organization import default_organization
from opencompany_core.workforce import default_workforce
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class OpenCompanyRuntime:
    store: SQLiteStore
    queue: DurableWorkerQueue
    worker: OpenCompanyWorker
    delegations: DelegationRepository
    sessions: OwnerSessionStore
    fleet: WorkerFleet
    gateway: ModelGateway
    handoffs: HandoffRepository
    learning: LearningRepository
    github_evolution: GitHubEvolutionClient | None
    api_anything: ApiAnythingClient | None
    secret_vault: ProviderSecretVault
    usage: ModelUsageRepository
    secret_vault_errors: dict[str, str]
    unorouter_tested_at: str | None = None
    github_evolution_tested_at: str | None = None

    def stop_workers_for_provider_change(self) -> None:
        """Stop inference before changing provider credentials or routing."""
        self.fleet.stop(timeout_seconds=5.0)
        if self.fleet.status().running:
            raise RuntimeError("worker fleet did not stop before provider configuration change")

    def configure_unorouter(
        self, configuration: dict[str, str] | None, *, workers_already_stopped: bool = False
    ) -> None:
        # Never swap provider credentials while an existing worker can still use
        # the old gateway. The API pre-stops before mutating the encrypted vault.
        if not workers_already_stopped:
            self.stop_workers_for_provider_change()
        self.gateway = (
            configured_unorouter_gateway(configuration)
            if configuration is not None else ModelGateway()
        )
        self.gateway.set_usage_recorder(self.usage.record)
        self.worker.executor._gateway = self.gateway
        broker = self.worker.executor._research_broker
        if broker is not None:
            broker.gateway = self.gateway
        self.unorouter_tested_at = None
        self.secret_vault_errors.pop("unorouter", None)

    def start_workers_if_ready(self) -> bool:
        """Start the fleet only after a successful owner test of a free provider."""
        enabled = os.environ.get("OPENCOMPANY_WORKER_AUTOSTART", "false").strip().casefold() in {"1", "true", "yes", "on"}
        if not enabled or not os.environ.get("OPENCOMPANY_OWNER_API_KEY", "").strip():
            return False
        if self.unorouter_tested_at is None:
            return False
        if not self.gateway.eligible_providers(request_budget_usd=0.0):
            return False
        return bool(self.fleet.start())

    def configure_github_evolution(self, token: str | None) -> None:
        if token is None:
            self.github_evolution = None
            self.github_evolution_tested_at = None
            self.secret_vault_errors.pop("github_evolution", None)
            return
        repository = os.environ.get("OPENCOMPANY_GITHUB_REPOSITORY", "").strip()
        base_branch = os.environ.get("OPENCOMPANY_GITHUB_BASE_BRANCH", "clean-room-rebuild").strip()
        if not repository:
            raise ValueError("OPENCOMPANY_GITHUB_REPOSITORY must be configured before saving a GitHub token")
        self.github_evolution = GitHubEvolutionClient(
            token, repository, base_branch=base_branch,
        )
        self.github_evolution_tested_at = None
        self.secret_vault_errors.pop("github_evolution", None)

    def close(self) -> None:
        # Queue shares the store connection; only the store owns its lifecycle.
        self.fleet.stop(timeout_seconds=5.0)
        self.delegations.close()
        self.store.close()


def create_runtime(database_path: str | None = None) -> OpenCompanyRuntime:
    """Build the API/worker composition without starting background workers."""
    configured = database_path or os.environ.get(
        "OPENCOMPANY_DATABASE_PATH", "data/opencompany_core.sqlite3"
    )
    path = Path(configured).expanduser()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(path)
    delegations = DelegationRepository(store._connection, store._lock)
    sessions = OwnerSessionStore(store._connection, store._lock)
    handoffs = HandoffRepository(store._connection, store._lock)
    learning = LearningRepository(store._connection, store._lock)
    secret_vault = ProviderSecretVault(store._connection, store._lock)
    usage = ModelUsageRepository(store._connection, store._lock)
    secret_vault_errors: dict[str, str] = {}
    try:
        stored_github = secret_vault.get("github_evolution")
    except Exception as exc:
        stored_github = None
        secret_vault_errors["github_evolution"] = "Stored GitHub token cannot be decrypted; replace it or remove it from the owner dashboard."
    if "github_evolution" in secret_vault_errors:
        github_evolution = None
    elif stored_github is not None and os.environ.get("OPENCOMPANY_GITHUB_REPOSITORY", "").strip():
        github_evolution = GitHubEvolutionClient(
            stored_github["token"],
            os.environ["OPENCOMPANY_GITHUB_REPOSITORY"].strip(),
            base_branch=os.environ.get("OPENCOMPANY_GITHUB_BASE_BRANCH", "clean-room-rebuild"),
        )
    else:
        github_evolution = GitHubEvolutionClient.from_env()
    queue = DurableWorkerQueue(
        store._connection,
        max_attempts=int(os.environ.get("OPENCOMPANY_WORKER_MAX_ATTEMPTS", "3")),
        lease_seconds=int(os.environ.get("OPENCOMPANY_WORKER_LEASE_SECONDS", "300")),
        lock=store._lock,
    )
    try:
        stored_unorouter = secret_vault.get("unorouter")
    except SecretVaultError:
        stored_unorouter = None
        secret_vault_errors["unorouter"] = "Stored UnoRouter credentials cannot be decrypted; replace them in the owner dashboard."
    if stored_unorouter is not None and stored_unorouter.get("model") != UNOROUTER_AUTO_FREE_MODEL:
        # Preserve the existing encrypted inference key while upgrading its
        # routing policy to automatic confirmed-free model rotation.
        try:
            secret_vault.put("unorouter", {
                "api_key": stored_unorouter["api_key"],
                "model": UNOROUTER_AUTO_FREE_MODEL,
            })
            stored_unorouter["model"] = UNOROUTER_AUTO_FREE_MODEL
        except SecretVaultError:
            stored_unorouter = None
            secret_vault_errors["unorouter"] = "Stored UnoRouter credentials could not be upgraded safely; review the owner dashboard."
    gateway = (
        ModelGateway()
        if "unorouter" in secret_vault_errors
        else configured_unorouter_gateway({
            "api_key": stored_unorouter["api_key"],
            "model": stored_unorouter["model"],
            "confirmed_free": "true",
        }) if stored_unorouter is not None else configured_unorouter_gateway()
    )
    gateway.set_usage_recorder(usage.record)
    api_anything = ApiAnythingClient.from_env()
    research_broker = ResearchBroker(api_anything, gateway) if api_anything is not None else None
    def read_dependency_deliverables(item):
        results = []
        for dependency_id in item.depends_on:
            deliverables = store.list_deliverables(dependency_id)
            if not deliverables:
                raise ValueError("completed prerequisite has no persisted deliverable")
            results.append({
                "work_item_id": str(dependency_id),
                "deliverables": [
                    {
                        "role_key": row["role_key"],
                        "content": row["content"][:8000],
                        "provider": row["provider"],
                        "model": row["model"],
                        "cost_usd": row["cost_usd"],
                    }
                    for row in deliverables[:5]
                ],
            })
        return results

    executor = AgentExecutor(
        gateway=gateway,
        learning_context=learning.list_learning_notes,
        research_broker=research_broker,
        usage_recorder=usage.record,
        dependency_context=read_dependency_deliverables,
    )
    def automatic_manager_review(work_item_id):
        """Run the manager quality gate after a specialist has durably delivered."""
        if os.environ.get("OPENCOMPANY_AUTO_MANAGER_REVIEW", "false").strip().casefold() not in {"1", "true", "yes", "on"}:
            return "completed_review_required"
        item = store.get_work_item(work_item_id)
        if item is None or item.state != TaskState.REVIEW or item.assigned_agent_id is None:
            return "completed_review_required"
        department = default_organization().get(item.department)
        manager_role_key = department.manager_role_key
        manager = next((agent for agent in store.list_agents(limit=1000)
                        if agent.department == item.department
                        and agent.role_key == manager_role_key
                        and agent.team_key == "management"
                        and agent.state == AgentState.ACTIVE), None)
        if manager is None:
            return "completed_review_required"
        specialist = store.get_agent(item.assigned_agent_id)
        if specialist is None or specialist.role_key == manager_role_key:
            return "completed_review_required"
        deliverables = store.list_deliverables(work_item_id)
        decision = review_specialist_deliverables(item, manager_role_key, deliverables, gateway)
        event = AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="agent",
            actor_id=str(manager.id),
            action="manager.specialist_review_accepted" if decision.approved else "manager.specialist_rework_requested",
            subject_type="work_item", subject_id=str(work_item_id),
            outcome="recorded", correlation_id=str(uuid4()),
            details={"manager_role_key": manager_role_key, "approved": decision.approved,
                     "rationale": decision.rationale, "rework_instructions": decision.rework_instructions,
                     "provider": decision.provider, "model": decision.model,
                     "trigger": "worker_post_delivery"},
        )
        state = store.review_work_item_with_audit(
            work_item_id, approved=decision.approved, rationale=decision.rationale, record=event,
        )
        if state is None:
            return "completed_review_required"
        if decision.approved:
            # Once the last specialist dependency is approved, automatically
            # admit its already-approved manager synthesis task when the
            # owner has enabled zero-cost auto-queueing.
            queued_synthesis_ids = []
            auto_queue_enabled = os.environ.get(
                "OPENCOMPANY_AUTO_QUEUE_APPROVED_WORK", "false"
            ).strip().casefold() in {"1", "true", "yes", "on"}
            if auto_queue_enabled and gateway.eligible_providers(request_budget_usd=0.0):
                completed_ids = {
                    value.id for value in store.list_work_items(limit=1000)
                    if value.state == TaskState.COMPLETED
                }
                for candidate in store.list_work_items(limit=1000):
                    if (
                        candidate.state != TaskState.READY
                        or work_item_id not in candidate.depends_on
                        or candidate.assigned_agent_id is None
                        or not set(candidate.depends_on).issubset(completed_ids)
                    ):
                        continue
                    proposals = delegations.list_for_parent(candidate.id)
                    if not any(value["status"] == "approved" for value in proposals):
                        continue
                    synthesis_manager = store.get_agent(candidate.assigned_agent_id)
                    expected_role = default_organization().get(candidate.department).manager_role_key
                    if (
                        synthesis_manager is None
                        or synthesis_manager.state != AgentState.ACTIVE
                        or synthesis_manager.department != candidate.department
                        or synthesis_manager.role_key != expected_role
                        or synthesis_manager.team_key != "management"
                    ):
                        store.append_audit_record(AuditRecord(
                            id=uuid4(), occurred_at=datetime.now(timezone.utc),
                            actor_type="system", actor_id="opencompany-manager-review",
                            action="manager.synthesis_queue_blocked",
                            subject_type="work_item", subject_id=str(candidate.id),
                            outcome="blocked", correlation_id=str(event.correlation_id),
                            details={"reason": "manager_profile_not_active_or_valid"},
                        ))
                        continue
                    try:
                        queue.enqueue_authorized(
                            candidate, synthesis_manager.id,
                            {"source": "automatic_manager_synthesis",
                             "manager_role_key": synthesis_manager.role_key},
                            AuditRecord(
                                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                                actor_type="agent", actor_id=str(manager.id),
                                action="manager.synthesis_auto_queued",
                                subject_type="work_item", subject_id=str(candidate.id),
                                outcome="queued", correlation_id=str(event.correlation_id),
                                details={"assigned_manager_id": str(synthesis_manager.id),
                                         "request_budget_usd": 0.0},
                            ),
                        )
                        queued_synthesis_ids.append(str(candidate.id))
                    except Exception as exc:
                        store.append_audit_record(AuditRecord(
                            id=uuid4(), occurred_at=datetime.now(timezone.utc),
                            actor_type="system", actor_id="opencompany-manager-review",
                            action="manager.synthesis_queue_unavailable",
                            subject_type="work_item", subject_id=str(candidate.id),
                            outcome="failed", correlation_id=str(event.correlation_id),
                            details={"error_type": type(exc).__name__},
                        ))
            return "manager_approved" if not queued_synthesis_ids else (
                "manager_approved_synthesis_queued:" + ",".join(queued_synthesis_ids)
            )
        # Rejected drafts return to the same specialist with explicit rework.
        updated = store.get_work_item(work_item_id)
        updated = replace(
            updated,
            objective=(updated.objective + "\n\nManager rework request: " + decision.rework_instructions)[:12000],
        )
        rework_event = AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="agent",
            actor_id=str(manager.id), action="manager.rework_instructions_attached",
            subject_type="work_item", subject_id=str(work_item_id), outcome="recorded",
            correlation_id=str(event.correlation_id),
            details={"instruction_length": len(decision.rework_instructions)},
        )
        store.save_work_item_with_audit(updated, rework_event)
        queue.enqueue_authorized(
            updated, specialist.id, {"source": "automatic_manager_rework", "manager_role_key": manager_role_key},
            AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="agent",
                actor_id=str(manager.id), action="manager.rework_auto_queued",
                subject_type="work_item", subject_id=str(work_item_id), outcome="queued",
                correlation_id=str(event.correlation_id),
                details={"specialist_role_key": specialist.role_key},
            ),
        )
        return "manager_rework_queued"

    auto_review_callback = automatic_manager_review if os.environ.get(
        "OPENCOMPANY_AUTO_MANAGER_REVIEW", "false"
    ).strip().casefold() in {"1", "true", "yes", "on"} else None
    worker = OpenCompanyWorker(
        queue=queue,
        store=store,
        executor=executor,
        artifact_sink=store,
        request_budget_usd=0.0,
        preferred_provider="unorouter",
        post_delivery_review=auto_review_callback,
    )
    worker_concurrency = int(os.environ.get("OPENCOMPANY_WORKER_CONCURRENCY", "2"))
    fleet = WorkerFleet(
        worker, store,
        idle_poll_seconds=float(os.environ.get("OPENCOMPANY_WORKER_IDLE_SECONDS", "2")),
        concurrency=worker_concurrency,
    )
    runtime = OpenCompanyRuntime(
        store=store, queue=queue, worker=worker, delegations=delegations,
        sessions=sessions, fleet=fleet, gateway=gateway, handoffs=handoffs,
        learning=learning, github_evolution=github_evolution, api_anything=api_anything,
        secret_vault=secret_vault,
        usage=usage,
        secret_vault_errors=secret_vault_errors,
    )
    # Runtime construction stays inert. For dashboard-managed credentials,
    # workers start only after the owner runs a successful provider test in
    # this process; a service restart therefore requires fresh verification.
    return runtime
