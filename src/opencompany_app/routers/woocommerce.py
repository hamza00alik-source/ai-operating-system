"""Owner-controlled, read-only WooCommerce connection and data import routes."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import AuditRecord
from opencompany_core.secret_vault import SecretVaultError
from opencompany_core.woocommerce_readonly import WooCommerceReadError, WooCommerceReadOnlyClient
from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.api_schemas import WooCommerceConnectionInput
from opencompany_app.runtime import OpenCompanyRuntime

router = APIRouter()
_BUSINESSES = {"physical-agency", "physical-brand", "digital-products"}


def _provider_key(business_id: str) -> str:
    if business_id not in _BUSINESSES:
        raise HTTPException(status_code=422, detail="Unknown commercial business unit.")
    return "woocommerce:" + business_id


def _client(runtime: OpenCompanyRuntime, business_id: str) -> WooCommerceReadOnlyClient:
    key = _provider_key(business_id)
    try:
        saved = runtime.secret_vault.get(key)
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored WooCommerce credentials cannot be decrypted.") from exc
    if saved is None:
        raise HTTPException(status_code=409, detail="No WooCommerce connection is configured for this business.")
    try:
        return WooCommerceReadOnlyClient(**saved)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Stored WooCommerce connection settings are invalid; replace the connection.") from exc


def _audit(runtime: OpenCompanyRuntime, business_id: str, action: str, outcome: str, details: dict) -> None:
    runtime.store.append_audit_record(AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type="business_integration", subject_id="woocommerce",
        outcome=outcome, correlation_id=str(uuid4()),
        details={"business_id": business_id, "provider": "woocommerce", **details},
    ))


@router.get("/integrations/woocommerce/{business_id}/status", dependencies=[Depends(require_owner_key)])
def woo_status(business_id: str, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    key = _provider_key(business_id)
    status = runtime.secret_vault.status(key)
    return {
        "provider": "woocommerce", "business_id": business_id,
        "configured": status["configured"], "credentials_encrypted": status["configured"],
        "updated_at": status["updated_at"], "revision": status["revision"],
        "mode": "read-only", "available_reads": ["products", "orders"],
        "writes_enabled": False, "customer_personal_data_returned": False,
        "connection_tested": False,
    }


@router.put("/integrations/woocommerce/{business_id}/connection", dependencies=[Depends(require_owner_key)])
def save_woo_connection(
    business_id: str, payload: WooCommerceConnectionInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    key = _provider_key(business_id)
    try:
        # Validate URL and key shape locally; saving does not contact the store.
        WooCommerceReadOnlyClient(payload.store_url, payload.consumer_key, payload.consumer_secret)
        revision = runtime.secret_vault.put(key, {
            "store_url": payload.store_url.strip().rstrip("/"),
            "consumer_key": payload.consumer_key,
            "consumer_secret": payload.consumer_secret,
        })
    except (ValueError, SecretVaultError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(runtime, business_id, "integration.woocommerce_credentials_saved", "encrypted", {
        "revision": revision, "network_request_made": False,
    })
    return {
        "provider": "woocommerce", "business_id": business_id,
        "configured": True, "credentials_encrypted": True,
        "revision": revision, "mode": "read-only",
        "network_request_made": False, "writes_enabled": False,
    }


@router.delete("/integrations/woocommerce/{business_id}/connection", dependencies=[Depends(require_owner_key)])
def disconnect_woo(business_id: str, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    key = _provider_key(business_id)
    deleted = runtime.secret_vault.delete(key)
    if deleted:
        _audit(runtime, business_id, "integration.woocommerce_disconnected", "removed", {})
    return {"provider": "woocommerce", "business_id": business_id, "disconnected": deleted}


@router.post("/integrations/woocommerce/{business_id}/test", dependencies=[Depends(require_owner_key)])
def test_woo_connection(business_id: str, runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    client = _client(runtime, business_id)
    try:
        result = client.products(page=1, per_page=1)
    except WooCommerceReadError as exc:
        _audit(runtime, business_id, "integration.woocommerce_connection_test", "failed", {
            "error": str(exc), "resource": "products",
        })
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _audit(runtime, business_id, "integration.woocommerce_connection_test", "succeeded", {
        "resource": "products", "records_returned": result["count"],
    })
    return {
        "provider": "woocommerce", "business_id": business_id,
        "connection_tested": True, "success": True,
        "read_only": True, "writes_enabled": False,
        "sample_products_returned": result["count"],
    }


@router.get("/integrations/woocommerce/{business_id}/products", dependencies=[Depends(require_owner_key)])
def read_woo_products(
    business_id: str, page: int = 1, per_page: int = 20,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    client = _client(runtime, business_id)
    try:
        result = client.products(page=page, per_page=per_page)
    except (WooCommerceReadError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _audit(runtime, business_id, "integration.woocommerce_products_read", "succeeded", {
        "page": page, "per_page": per_page, "records_returned": result["count"],
    })
    return {"provider": "woocommerce", "business_id": business_id, **result, "read_only": True}


@router.get("/integrations/woocommerce/{business_id}/orders", dependencies=[Depends(require_owner_key)])
def read_woo_orders(
    business_id: str, page: int = 1, per_page: int = 20,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    client = _client(runtime, business_id)
    try:
        result = client.orders(page=page, per_page=per_page)
    except (WooCommerceReadError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _audit(runtime, business_id, "integration.woocommerce_orders_read", "succeeded", {
        "page": page, "per_page": per_page, "records_returned": result["count"],
        "customer_personal_data_returned": False,
    })
    return {"provider": "woocommerce", "business_id": business_id, **result, "read_only": True}
