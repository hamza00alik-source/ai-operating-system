"""Owner-controlled worker queue and execution lifecycle routes."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import BUSINESS_UNIT_IDS, AgentState, AuditRecord, TaskState
from opencompany_core.worker_queue import QueueError
from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


@router.get("/workers/queue", dependencies=[Depends(require_owner_key)])
def worker_queue_status(
    business_id: str | None = None,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    counts = runtime.queue.counts(business_id=business_id)
    status = runtime.fleet.status()
    return {
        "business_id": business_id or "all",
        "counts": counts,
        "total": sum(counts.values()),
        "worker_process_autostarted": status.running,
        "execution_requires_explicit_worker_process": not status.running,
        "worker_autostart_configured": os.environ.get("OPENCOMPANY_WORKER_AUTOSTART", "false").casefold() == "true",
        "free_provider_ready": bool(runtime.gateway.eligible_providers(request_budget_usd=0.0)),
        "product_rd_automation_enabled": status.maintenance_enabled,
        "product_rd_auto_proposals_enabled": runtime.product_rd_auto_proposals_enabled,
        "product_rd_automation_cycles": status.maintenance_cycles,
        "product_rd_automation_failures": status.maintenance_failures,
    }


@router.get("/workers/status", dependencies=[Depends(require_owner_key)])
def worker_fleet_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    status = runtime.fleet.status()
    return {
        "running": status.running,
        "concurrency": status.concurrency,
        "completed_cycles": status.completed_cycles,
        "idle_cycles": status.idle_cycles,
        "failed_cycles": status.failed_cycles,
        "active_agent_profiles": sum(
            1 for agent in runtime.store.list_agents(limit=1000)
            if agent.state == AgentState.ACTIVE and agent.role_key
        ),
        "product_rd_automation_enabled": status.maintenance_enabled,
        "product_rd_automation_cycles": status.maintenance_cycles,
        "product_rd_automation_failures": status.maintenance_failures,
    }


@router.post("/workers/start", dependencies=[Depends(require_owner_key)])
def start_worker_fleet(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(status_code=503, detail="No owner-configured free inference provider is available; worker start is blocked.")
    if runtime.unorouter_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the owner-triggered zero-cost UnoRouter test in this process before starting workers.")
    started = runtime.fleet.start()
    return {"running": bool(started) or runtime.fleet.status().running, "started_now": bool(started)}


@router.post("/workers/stop", dependencies=[Depends(require_owner_key)])
def stop_worker_fleet(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    stopped = runtime.fleet.stop(timeout_seconds=10.0)
    return {"running": runtime.fleet.status().running, "stopped_now": stopped}


@router.post("/work-items/{work_item_id}/cancel", dependencies=[Depends(require_owner_key)])
def cancel_work_item(
    work_item_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-request cancellation of queued or executing internal work."""
    item = runtime.store.get_work_item(work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    if item.state not in {TaskState.QUEUED, TaskState.IN_PROGRESS, TaskState.CANCELLED}:
        raise HTTPException(status_code=409, detail="Only queued or executing work can be cancelled.")
    record = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action="work_item.cancellation_requested",
        subject_type="work_item", subject_id=str(work_item_id), outcome="recorded",
        correlation_id=str(uuid4()), details={"business_id": item.business_id},
    )
    try:
        result = runtime.queue.request_cancel(work_item_id, record)
    except QueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    current = runtime.store.get_work_item(work_item_id)
    return {
        "work_item_id": str(work_item_id),
        "result": result,
        "task_state": current.state.value if current else None,
        "note": (
            "Cancellation is recorded. The active model request may need to finish before the worker can finalize it."
            if result == "cancellation_requested" else "Work was cancelled."
        ),
    }


@router.post("/workers/{agent_id}/run-once", dependencies=[Depends(require_owner_key)])
def run_agent_once(
    agent_id: UUID,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-trigger one bounded internal worker cycle for one active profile."""
    if runtime.unorouter_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the owner-triggered zero-cost UnoRouter test in this process before executing a worker cycle.")
    agent = runtime.store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    if agent.state != AgentState.ACTIVE or not agent.role_key:
        raise HTTPException(status_code=409, detail="Agent must be explicitly ACTIVE with a role.")
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(status_code=503, detail="No owner-configured free inference provider is available; worker execution is blocked.")
    try:
        result = runtime.worker.run_once(agent.id, agent.role_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Worker cycle failed: {type(exc).__name__}") from exc
    return {"agent_id": str(agent.id), "role_key": agent.role_key, "result": result}

