"""Owner-authenticated, read-only API Anything integration routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.api_anything import ApiAnythingError
from opencompany_app.api_schemas import ApiAnythingCallInput, ApiAnythingBatchInput
from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


@router.get("/integrations/api-anything/status", dependencies=[Depends(require_owner_key)])
def api_anything_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        return {"enabled": False, "mode": "read-only", "max_tier": 1, "writes_enabled": False}
    try:
        health = runtime.api_anything.health()
        return {
            "enabled": True, "mode": "read-only", "max_tier": 1,
            "writes_enabled": False, "health": health,
        }
    except ApiAnythingError as exc:
        return {"enabled": True, "mode": "read-only", "writes_enabled": False, "healthy": False, "error": str(exc)}


@router.get("/integrations/api-anything/sites", dependencies=[Depends(require_owner_key)])
def api_anything_sites(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        return runtime.api_anything.list_sites()
    except ApiAnythingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/integrations/api-anything/find", dependencies=[Depends(require_owner_key)])
def api_anything_find(q: str, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        return runtime.api_anything.find_sites(q)
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/integrations/api-anything/sites/{site}/operations", dependencies=[Depends(require_owner_key)])
def api_anything_operations(site: str, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        return runtime.api_anything.list_operations(site)
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/integrations/api-anything/call", dependencies=[Depends(require_owner_key)])
def api_anything_read_call(
    payload: ApiAnythingCallInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        result = runtime.api_anything.call_read(
            payload.site, payload.operation, payload.args, max_age_ms=payload.max_age_ms
        )
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": "read-only", "max_tier": 1, "result": result}


@router.post("/integrations/api-anything/batch", dependencies=[Depends(require_owner_key)])
def api_anything_read_batch(
    payload: ApiAnythingBatchInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if runtime.api_anything is None:
        raise HTTPException(status_code=503, detail="API Anything integration is not configured.")
    try:
        result = runtime.api_anything.call_batch(payload.calls)
    except (ApiAnythingError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": "read-only", "max_tier": 1, "result": result}

