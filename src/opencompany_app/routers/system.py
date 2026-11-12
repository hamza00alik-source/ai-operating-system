"""Liveness and readiness probes for the OpenCompany service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.platform import PLATFORM_ID, PLATFORM_NAME, PLATFORM_VERSION
from opencompany_app.api_dependencies import get_runtime
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: the ASGI process is responsive."""
    return {"status": "ok", "service": PLATFORM_ID, "product": PLATFORM_NAME, "version": PLATFORM_VERSION, "mode": "owner-authenticated"}


@router.get("/ready")
def readiness(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Readiness probe: owner configuration and persistent storage are usable.

    Provider readiness is intentionally not required here: the owner dashboard
    must be reachable before the owner can configure the free provider.
    """
    try:
        with runtime.store._lock:
            connection = runtime.store._connection
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or str(result[0]).casefold() != "ok":
                raise RuntimeError("database integrity check failed")
            connection.execute("SELECT 1").fetchone()
            # A readable database is not necessarily writable (for example,
            # when a persistent volume is mounted with the wrong owner).
            # Acquire and release a write transaction so readiness catches
            # that deployment failure before owner login attempts to create
            # a session or other state.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ROLLBACK")
        fleet = runtime.fleet.status()
    except Exception as exc:
        # Keep internal database and filesystem diagnostics out of public probes.
        raise HTTPException(status_code=503, detail="OpenCompany storage is not ready.") from exc
    return {
        "status": "ready",
        "service": PLATFORM_ID,
        "product": PLATFORM_NAME,
        "version": PLATFORM_VERSION,
        "storage": "ok",
        "worker_fleet_running": fleet.running,
        "provider_required_for_readiness": False,
    }
