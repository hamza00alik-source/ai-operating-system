"""Owner-only operational backup, usage and audit diagnostics."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
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


@diagnostics_router.get("/automation/jobs", dependencies=[Depends(require_owner_key)])
def automation_jobs(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Owner-only status for persisted automation schedules."""
    scheduler = runtime.automation_scheduler
    return {
        "enabled": scheduler is not None,
        "jobs": list(scheduler.status()) if scheduler is not None else [],
    }


@diagnostics_router.get("/automation/history", dependencies=[Depends(require_owner_key)])
def automation_history(
    job_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-only bounded execution history; never exposes callback payloads."""
    scheduler = runtime.automation_scheduler
    return {
        "enabled": scheduler is not None,
        "runs": list(scheduler.history(job_id=job_id, limit=limit)) if scheduler is not None else [],
    }


@diagnostics_router.get("/audit/verify", dependencies=[Depends(require_owner_key)])
def verify_audit(store: SQLiteStore = Depends(get_store)) -> dict:
    return {
        "event_count": store.audit_event_count(),
        "chain_valid": store.verify_audit_chain(),
    }

@diagnostics_router.get("/owner/production-readiness", dependencies=[Depends(require_owner_key)])
def production_readiness_snapshot(
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    """Owner-only evidence snapshot; never declares a release approved."""
    database = runtime.store.database
    is_memory = database == ":memory:"
    path = None if is_memory else os.path.abspath(os.path.expanduser(database))
    parent = os.path.dirname(path) if path else None
    try:
        with runtime.store._lock:
            connection = runtime.store._connection
            integrity_row = connection.execute("PRAGMA quick_check").fetchone()
            integrity_ok = bool(integrity_row and str(integrity_row[0]).casefold() == "ok")
            journal_row = connection.execute("PRAGMA journal_mode").fetchone()
            journal_mode = str(journal_row[0]).casefold() if journal_row else "unknown"
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            connection.execute("SELECT 1").fetchone()
        audit_valid = runtime.store.verify_audit_chain()
    except Exception:
        integrity_ok = False
        journal_mode = "unavailable"
        schema_version = None
        audit_valid = False
    fleet = runtime.fleet.status()
    parent_exists = bool(parent and os.path.isdir(parent))
    database_exists = bool(path and os.path.isfile(path))
    database_under_data = bool(path and os.path.commonpath([path, "/data"]) == "/data")
    checks = {
        "database_not_in_memory": not is_memory,
        "database_file_exists": database_exists,
        "database_path_under_persistent_data_mount": database_under_data,
        "database_parent_writable": bool(parent_exists and os.access(parent, os.W_OK)),
        "sqlite_integrity_check": integrity_ok,
        "audit_chain_valid": audit_valid,
        "schema_version_current": schema_version == 8,
        "secret_encryption_key_configured": bool(os.environ.get("OPENCOMPANY_SECRET_ENCRYPTION_KEY")),
        "owner_api_key_configured": bool(os.environ.get("OPENCOMPANY_OWNER_API_KEY")),
        "secure_cookie_configured": os.environ.get("OPENCOMPANY_COOKIE_SECURE", "false").casefold() == "true",
        "worker_fleet_stopped_for_maintenance": not fleet.running,
    }
    return {
        "status": "evidence_snapshot_only",
        "checks": checks,
        "sqlite": {"journal_mode": journal_mode, "schema_version": schema_version},
        "worker_fleet_running": fleet.running,
        "tests_and_ci": "not_verified_by_this_endpoint",
        "independent_security_review": "not_verified",
        "backup_restore_rehearsal": "not_verified",
        "staging_acceptance": "not_verified",
        "production_cutover_authorized": False,
        "note": "This diagnostic is not a production-readiness certification and performs no deployment or configuration changes.",
    }

