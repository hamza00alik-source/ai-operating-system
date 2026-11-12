"""Owner-authenticated UnoRouter configuration, discovery and inference-test endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from opencompany_core.unorouter_adapter import (
    UNOROUTER_AUTO_FREE_MODEL,
    discover_free_models,
    discover_model_catalog,
    unorouter_configuration_status,
)
from opencompany_core.secret_vault import SecretVaultError
from opencompany_core.model_gateway import CostPolicyViolation, ModelRequest, NoEligibleProvider, ProviderUnavailable
from opencompany_app.api_schemas import UnoRouterDiscoveryInput, UnoRouterSettingsInput
from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()

def _discover_free_models(api_key: str, *, force_refresh: bool = False):
    from opencompany_app import api as api_module
    try:
        if force_refresh:
            return api_module.discover_free_models(api_key, force_refresh=True)
        return api_module.discover_free_models(api_key)
    except TypeError as exc:
        if "force_refresh" not in str(exc):
            raise
        return api_module.discover_free_models(api_key)
    except ProviderUnavailable:
        return None

# In-memory owner-authenticated provider-test jobs; clients poll bounded jobs
# because an inference request can outlive browser/proxy request timeouts.
_UNOROUTER_TESTS: dict[str, dict] = {}
_UNOROUTER_TESTS_LOCK = Lock()
_UNOROUTER_TESTS_MAX = 50




@router.post("/settings/providers/unorouter/discover", dependencies=[Depends(require_owner_key)])
def discover_unorouter_models(payload: UnoRouterDiscoveryInput) -> dict:
    try:
        models = _discover_free_models(payload.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"UnoRouter model discovery failed safely: {exc}") from exc
    return {"success": True, "models": models, "count": len(models),
            "source": "authenticated-key-list intersected with live zero-price catalogue",
            "paid_models_included": False}


@router.get("/settings/providers/unorouter", dependencies=[Depends(require_owner_key)])
def get_unorouter_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    status = runtime.secret_vault.status("unorouter")
    configuration_error = None
    try:
        saved = runtime.secret_vault.get("unorouter")
    except SecretVaultError:
        saved = None
        configuration_error = "Stored UnoRouter credentials cannot be decrypted. Check the stable server encryption key, or replace/remove the saved credentials."
    return {
        "configured": saved is not None, "model": saved["model"] if saved else None,
        "api_key_present": status["configured"], "credentials_decryptable": saved is not None,
        "configuration_error": configuration_error or runtime.secret_vault_errors.get("unorouter"),
        "real_inference_verified": runtime.unorouter_tested_at is not None,
        "last_tested_at": runtime.unorouter_tested_at, "automatic_paid_fallback": False,
        **status,
    }


@router.get("/settings/providers/unorouter/models", dependencies=[Depends(require_owner_key)])
def list_unorouter_free_models(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Discover all free models accessible to the already-saved inference key."""
    try:
        saved = runtime.secret_vault.get("unorouter")
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored UnoRouter credentials cannot be decrypted.") from exc
    if not saved:
        raise HTTPException(status_code=409, detail="Save the UnoRouter API key first.")
    try:
        models = _discover_free_models(saved["api_key"], force_refresh=True)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"UnoRouter catalogue refresh failed safely: {exc}") from exc
    return {
        "provider": "unorouter", "count": len(models), "models": list(models),
        "routing_mode": "automatic_all_free_models",
        "catalogue_cache_seconds": 300, "paid_models_included": False,
        "paid_fallback": False,
    }


@router.get("/settings/providers/unorouter/catalog", dependencies=[Depends(require_owner_key)])
def import_unorouter_catalog(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Import the full live catalogue; paid/unsupported models are visible but hard-blocked."""
    try:
        saved = runtime.secret_vault.get("unorouter")
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored UnoRouter credentials cannot be decrypted.") from exc
    if not saved:
        raise HTTPException(status_code=409, detail="Save the UnoRouter API key first.")
    try:
        catalog = discover_model_catalog(saved["api_key"])
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"UnoRouter full catalogue import failed safely: {exc}") from exc
    eligible = [item for item in catalog if item["allowed_for_inference"]]
    blocked = len(catalog) - len(eligible)
    return {
        "provider": "unorouter",
        "source": "live public pricing catalogue intersected with authenticated /v1/models",
        "total_models": len(catalog),
        "eligible_free_chat_models": len(eligible),
        "blocked_models": blocked,
        "paid_models_included_for_inference": False,
        "paid_fallback": False,
        "policy": "FREE_ONLY_ZERO_PRICE_ONLINE_CHAT_KEY_ACCESS_REQUIRED",
        "models": list(catalog),
    }


@router.put("/settings/providers/unorouter", dependencies=[Depends(require_owner_key)])
def save_unorouter_settings(payload: UnoRouterSettingsInput, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if payload.confirm_free is not True:
        raise HTTPException(status_code=422, detail="Owner must explicitly confirm the selected model is free.")
    if payload.model != UNOROUTER_AUTO_FREE_MODEL and not payload.model.endswith(":free"):
        raise HTTPException(status_code=422, detail="Only explicitly free model IDs or automatic free-catalog routing are accepted.")
    if payload.model != UNOROUTER_AUTO_FREE_MODEL:
        discovered = _discover_free_models(payload.api_key)
        if discovered is not None and payload.model not in discovered:
            raise HTTPException(status_code=409, detail="The selected model is not currently listed as free, online, and available to this API key. Load the free-model list again.")
    try:
        runtime.stop_workers_for_provider_change()
        revision = runtime.secret_vault.put("unorouter", {"api_key": payload.api_key, "model": payload.model})
        runtime.configure_unorouter(
            {"api_key": payload.api_key, "model": payload.model, "confirmed_free": "true"},
            workers_already_stopped=True,
        )
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Workers are still processing; provider settings were not changed.") from exc
    return {"configured": True, "model": payload.model, "api_key_saved": True, "revision": revision,
            "billing_mode": "free_confirmed", "automatic_paid_fallback": False, "live_inference_tested": False}


def _worker_autostart_enabled() -> bool:
    return os.environ.get("OPENCOMPANY_WORKER_AUTOSTART", "false").strip().casefold() in {"1", "true", "yes", "on"}


def _run_unorouter_test(runtime: OpenCompanyRuntime, job_id: str) -> None:
    with _UNOROUTER_TESTS_LOCK:
        job = _UNOROUTER_TESTS.get(job_id)
        if job is None:
            return
        job["status"] = "running"
    try:
        result = runtime.gateway.complete(
            ModelRequest(prompt="Reply with exactly: OPENCOMPANY_UNOROUTER_OK",
                         request_id=f"owner-unorouter-test-{uuid4()}", max_output_tokens=24),
            request_budget_usd=0.0, preferred_provider="unorouter",
        )
        if result.text.strip() != "OPENCOMPANY_UNOROUTER_OK":
            raise ProviderUnavailable("UnoRouter returned an unexpected test response.")
        runtime.unorouter_tested_at = datetime.now(timezone.utc).isoformat()
        worker_started = False
        worker_start_error = None
        try:
            worker_started = runtime.start_workers_if_ready()
        except Exception as exc:
            worker_start_error = type(exc).__name__
        outcome = {
            "status": "succeeded", "success": True, "provider": result.provider,
            "model": result.model, "cost_usd": result.cost_usd,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            "output_preview": result.text[:160], "tested_at": runtime.unorouter_tested_at,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": worker_started, "worker_start_error": worker_start_error,
            "paid_fallback": False,
        }
    except NoEligibleProvider:
        outcome = {
            "status": "failed", "success": False,
            "error": "No confirmed-free UnoRouter model is configured and available.",
            "provider": "unorouter", "model": None, "cost_usd": 0.0,
            "input_tokens": 0, "output_tokens": 0, "output_preview": None,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": False, "worker_start_error": None, "paid_fallback": False,
        }
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        # Adapter diagnostics are deliberately bounded and contain no credentials.
        reason = " ".join(str(exc).split())[:600] or type(exc).__name__
        outcome = {
            "status": "failed", "success": False,
            "error": f"UnoRouter test failed safely: {reason}. No paid fallback was attempted.",
            "provider": "unorouter", "model": None, "cost_usd": 0.0,
            "input_tokens": 0, "output_tokens": 0, "output_preview": None,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": False, "worker_start_error": None, "paid_fallback": False,
        }
    except Exception as exc:
        outcome = {
            "status": "failed", "success": False,
            "error": f"UnoRouter test failed safely ({type(exc).__name__}). No paid fallback was attempted.",
            "provider": "unorouter", "model": None, "cost_usd": 0.0,
            "input_tokens": 0, "output_tokens": 0, "output_preview": None,
            "worker_autostart_enabled": _worker_autostart_enabled(),
            "worker_started": False, "worker_start_error": None, "paid_fallback": False,
        }
    with _UNOROUTER_TESTS_LOCK:
        if job_id in _UNOROUTER_TESTS:
            _UNOROUTER_TESTS[job_id].update(outcome)


@router.post("/settings/providers/unorouter/test", dependencies=[Depends(require_owner_key)])
def test_unorouter_connection(
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> JSONResponse:
    # A browser/proxy can close a long-running inference request. Start the
    # bounded zero-dollar test in a background task and let the owner poll it.
    with _UNOROUTER_TESTS_LOCK:
        active = next((
            job for job in reversed(list(_UNOROUTER_TESTS.values()))
            if job.get("status") in {"queued", "running"}
        ), None)
        if active is not None:
            return JSONResponse(status_code=202, content={
                "job_id": active["job_id"], "status": active["status"],
            })
        job_id = str(uuid4())
        _UNOROUTER_TESTS[job_id] = {"job_id": job_id, "status": "queued"}
        while len(_UNOROUTER_TESTS) > _UNOROUTER_TESTS_MAX:
            oldest = next(iter(_UNOROUTER_TESTS))
            if _UNOROUTER_TESTS[oldest].get("status") in {"queued", "running"}:
                break
            _UNOROUTER_TESTS.pop(oldest, None)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "queued"},
        background=BackgroundTask(_run_unorouter_test, runtime, job_id),
    )


@router.get("/settings/providers/unorouter/test/{job_id}", dependencies=[Depends(require_owner_key)])
def get_unorouter_test_status(job_id: UUID) -> dict:
    with _UNOROUTER_TESTS_LOCK:
        job = _UNOROUTER_TESTS.get(str(job_id))
        if job is None:
            raise HTTPException(status_code=404, detail="UnoRouter test job was not found or has expired.")
        return dict(job)


@router.delete("/settings/providers/unorouter", dependencies=[Depends(require_owner_key)])
def remove_unorouter_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    try:
        runtime.stop_workers_for_provider_change()
        removed = runtime.secret_vault.delete("unorouter")
        runtime.configure_unorouter(None, workers_already_stopped=True)
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored provider settings could not be removed safely.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Workers are still processing; provider settings were not changed.") from exc
    return {"removed": removed, "configured": False, "paid_fallback": False}
