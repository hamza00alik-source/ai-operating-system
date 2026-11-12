"""Composition root for the independent OpenCompany runtime.

The API and worker process share one SQLite database. Queue admission, queue
claim, task-state transitions, and audit events therefore use one transaction
boundary. Importing this module never starts a worker.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
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
from opencompany_core.secret_vault import BusinessCredentialVault, ProviderSecretVault, SecretVaultError
from opencompany_core.integration_registry import BusinessIntegrationRegistry
from opencompany_core.business_memory import BusinessMemoryStore
from opencompany_core.business_assets import BusinessAssetRegistry
from opencompany_core.asset_storage import PrivateFilesystemAssetStorage
from opencompany_core.asset_scanning import ClamAVUnixSocketScanner
from opencompany_core.model_usage import ModelUsageRepository


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
    business_credentials: BusinessCredentialVault
    integrations: BusinessIntegrationRegistry
    business_memory: BusinessMemoryStore
    business_assets: BusinessAssetRegistry
    asset_storage: PrivateFilesystemAssetStorage | None
    asset_scanner: ClamAVUnixSocketScanner | None
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


def _read_dependency_deliverables(store, item):
    results = []
    for dependency_id in item.depends_on:
        prerequisite = store.get_work_item(dependency_id)
        if prerequisite is None:
            raise ValueError("work dependency does not exist")
        if prerequisite.business_id != item.business_id:
            raise ValueError("work dependency belongs to another business unit")
        if prerequisite.state.value != "completed":
            raise ValueError("work dependency is not completed")
        deliverables = store.list_deliverables(dependency_id)
        if not deliverables:
            raise ValueError("completed prerequisite has no persisted deliverable")
        results.append({
            "work_item_id": str(dependency_id),
            "business_id": prerequisite.business_id,
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
    business_credentials = BusinessCredentialVault(store._connection, store._lock)
    integrations = BusinessIntegrationRegistry(store._connection, store._lock)
    business_memory = BusinessMemoryStore(store._connection, store._lock)
    business_assets = BusinessAssetRegistry(store._connection, store._lock)
    asset_storage_path = os.environ.get("OPENCOMPANY_ASSET_STORAGE_PATH", "").strip()
    asset_storage = None
    if asset_storage_path:
        durable_confirmed = os.environ.get("OPENCOMPANY_ASSET_STORAGE_DURABLE", "false").strip().casefold() in {"1", "true", "yes", "on"}
        storage_path = Path(asset_storage_path).expanduser()
        data_mount = Path("/data")
        if not durable_confirmed or not storage_path.is_absolute() or ".." in storage_path.parts or storage_path == data_mount or not storage_path.is_relative_to(data_mount):
            raise RuntimeError("asset storage requires an absolute path under /data and OPENCOMPANY_ASSET_STORAGE_DURABLE=true")
        if not data_mount.is_mount():
            raise RuntimeError("asset storage is disabled because /data is not verified as a mounted persistent volume")
        asset_storage = PrivateFilesystemAssetStorage(storage_path)
    clamd_socket_path = os.environ.get("OPENCOMPANY_CLAMD_SOCKET_PATH", "").strip()
    asset_scanner = (
        ClamAVUnixSocketScanner(
            clamd_socket_path,
            timeout_seconds=float(os.environ.get("OPENCOMPANY_CLAMD_TIMEOUT_SECONDS", "120")),
        )
        if clamd_socket_path else None
    )
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
    executor = AgentExecutor(
        gateway=gateway,
        learning_context=learning.list_learning_notes,
        research_broker=research_broker,
        usage_recorder=usage.record,
        dependency_context=lambda item: _read_dependency_deliverables(store, item),
    )
    worker = OpenCompanyWorker(
        queue=queue,
        store=store,
        executor=executor,
        artifact_sink=store,
        request_budget_usd=0.0,
        preferred_provider="unorouter",
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
        business_credentials=business_credentials,
        integrations=integrations,
        business_memory=business_memory,
        business_assets=business_assets,
        asset_storage=asset_storage,
        asset_scanner=asset_scanner,
        usage=usage,
        secret_vault_errors=secret_vault_errors,
    )
    # Runtime construction stays inert. For dashboard-managed credentials,
    # workers start only after the owner runs a successful provider test in
    # this process; a service restart therefore requires fresh verification.
    return runtime
