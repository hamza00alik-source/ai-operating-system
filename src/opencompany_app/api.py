"""Standalone OpenCompany API, independent of legacy AIOS modules.

The service exposes a public read-only health check. Company records and
write operations require owner authentication. Model calls are cost-gated to explicitly configured free providers; external business actions remain outside the runtime's authority.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from opencompany_core.platform import PLATFORM_NAME, PLATFORM_VERSION


from opencompany_core.provisioning import bootstrap_department_managers, bootstrap_specialist_profiles, bootstrap_executive_orchestrator
from opencompany_app.api_dependencies import (
    _default_runtime, get_runtime, get_store, get_delegation_store, require_owner_key,
)
from opencompany_app.routers.catalogue import router as catalogue_router
from opencompany_app.routers.system import router as system_router
from opencompany_app.routers.dashboard import router as dashboard_router
from opencompany_app.routers.providers import router as providers_router, _worker_autostart_enabled
from opencompany_app.routers.github_evolution import settings_router as github_settings_router, evolution_router as github_evolution_router
from opencompany_app.routers.integrations import router as integrations_router
from opencompany_app.routers.agents import router as agents_router
from opencompany_app.routers.commercial import router as commercial_router, supplier_router as commercial_supplier_router
from opencompany_app.routers.workers import router as workers_router
from opencompany_app.routers.work_items import router as work_items_router
from opencompany_app.routers.handoffs import router as handoffs_router
from opencompany_app.routers.orchestration import router as orchestration_router
from opencompany_app.routers.lifecycle import router as lifecycle_router
from opencompany_app.routers.learning import router as learning_router
from opencompany_app.routers.portfolio import router as portfolio_router
from opencompany_app.routers.auth import router as auth_router
from opencompany_app.routers.operations import backup_router as operations_backup_router, diagnostics_router as operations_diagnostics_router
from opencompany_app.routers.planning import planning_router, queue_router, delegation_router
from opencompany_app.routers.provider_info import provider_status_router, provider_candidates_router, executive_portfolio_router


app = FastAPI(
    title=PLATFORM_NAME,
    version=PLATFORM_VERSION,
    description="Unified OpenCompany AIOS platform: one independently authored engine, company runtime, and owner console.",
)

# Per-process login throttling. The API key is a bootstrap credential; this
# protects the session exchange endpoint from unlimited online guessing.
_LOGGER = logging.getLogger(__name__)


@app.on_event("startup")
def initialize_autonomous_runtime() -> None:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        return
    bootstrap_enabled = os.environ.get("OPENCOMPANY_BOOTSTRAP_WORKFORCE", "false").casefold() == "true"
    activate_enabled = os.environ.get("OPENCOMPANY_AUTO_ACTIVATE_WORKFORCE", "false").casefold() == "true"
    autostart_enabled = _worker_autostart_enabled()
    if not (bootstrap_enabled or activate_enabled or autostart_enabled):
        return
    runtime = _default_runtime()
    if bootstrap_enabled:
        bootstrap_department_managers(runtime.store)
        bootstrap_specialist_profiles(runtime.store)
        bootstrap_executive_orchestrator(runtime.store)
    if activate_enabled:
        runtime.store.activate_all_draft_agents_with_audit()
    # Autostart is an explicit owner-controlled deployment setting. The gateway
    # still enforces the live strict-free catalogue and a zero-dollar request
    # budget for every inference call; unavailable free models fail closed.
    if autostart_enabled:
        try:
            if runtime.gateway.eligible_providers(request_budget_usd=0.0):
                runtime.fleet.start()
            else:
                _LOGGER.warning("Worker autostart was requested but no confirmed-free provider is configured.")
        except Exception:
            _LOGGER.exception("Worker autostart could not initialize safely; workers remain stopped.")


@app.on_event("shutdown")
def close_autonomous_runtime() -> None:
    if _default_runtime.cache_info().currsize:
        _default_runtime().close()
        _default_runtime.cache_clear()





app.include_router(dashboard_router)
app.include_router(system_router)
app.include_router(provider_status_router)
app.include_router(operations_backup_router)


app.include_router(catalogue_router)


app.include_router(providers_router)

app.include_router(github_settings_router)
app.include_router(provider_candidates_router)




app.include_router(planning_router)
app.include_router(agents_router)
app.include_router(commercial_router)


app.include_router(work_items_router)
app.include_router(queue_router)


app.include_router(workers_router)
app.include_router(delegation_router)


app.include_router(integrations_router)


app.include_router(github_evolution_router)
app.include_router(learning_router)


app.include_router(handoffs_router)


app.include_router(orchestration_router)
app.include_router(lifecycle_router)


app.include_router(commercial_supplier_router)
app.include_router(portfolio_router)
app.include_router(executive_portfolio_router)
app.include_router(auth_router)
app.include_router(operations_diagnostics_router)

