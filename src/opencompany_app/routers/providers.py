"""Owner-authenticated UnoRouter discovery and read-only settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.unorouter_adapter import (
    discover_free_models,
    discover_model_catalog,
    unorouter_configuration_status,
)
from opencompany_core.secret_vault import SecretVaultError
from opencompany_core.model_gateway import ProviderUnavailable
from opencompany_app.api_schemas import UnoRouterDiscoveryInput
from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


@router.post("/settings/providers/unorouter/discover", dependencies=[Depends(require_owner_key)])
def discover_unorouter_models(payload: UnoRouterDiscoveryInput) -> dict:
    try:
        models = discover_free_models(payload.api_key)
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
        models = discover_free_models(saved["api_key"], force_refresh=True)
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
