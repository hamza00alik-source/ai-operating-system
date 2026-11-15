"""Owner-only operational backup, usage and audit diagnostics."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from opencompany_core.domain import BUSINESS_UNIT_IDS
from opencompany_core.persistence import SQLiteStore
from opencompany_app.api_dependencies import get_runtime, get_store, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


backup_router = APIRouter()
diagnostics_router = APIRouter()


@backup_router.get("/owner/backup", dependencies=[Depends(require_owner_key)])
def download_owner_database_backup(store: SQLiteStore = Depends(get_store)) -> FileResponse:
    """Download a consistent, integrity-checked SQLite snapshot for owner backup."""
    descriptor, backup_path = tempfile.mkstemp(prefix="opencompany-backup-", suffix=".sqlite3")
    os.close(descriptor)
    try:
        store.backup_to(backup_path)
    except Exception as exc:
        try:
            os.unlink(backup_path)
        except FileNotFoundError:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Database backup failed safely: {type(exc).__name__}",
        ) from exc
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return FileResponse(
        backup_path,
        media_type="application/vnd.sqlite3",
        filename=f"opencompany-backup-{stamp}.sqlite3",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        background=BackgroundTask(os.unlink, backup_path),
    )


@diagnostics_router.get("/usage/model", dependencies=[Depends(require_owner_key)])
def model_usage_summary(
    business_id: str | None = None,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-only, durable inference usage and cost accounting, optionally scoped by business."""
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")
    return runtime.usage.summary(limit=100, business_id=business_id)


@diagnostics_router.get("/audit/verify", dependencies=[Depends(require_owner_key)])
def verify_audit(store: SQLiteStore = Depends(get_store)) -> dict:
    return {
        "event_count": store.audit_event_count(),
        "chain_valid": store.verify_audit_chain(),
    }
