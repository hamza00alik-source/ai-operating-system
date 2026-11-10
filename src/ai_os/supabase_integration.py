"""Owner-controlled Supabase/PostgreSQL connection diagnostics.

This adapter deliberately exposes no database credentials and performs no schema
changes. Schema migrations remain a separate, explicitly approved operation.
"""
from __future__ import annotations

from time import monotonic
from urllib.parse import urlsplit

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from ai_os.auth import require_owner_key
from ai_os.config import get_settings

router = APIRouter(
    prefix="/integrations/supabase",
    tags=["Supabase integration"],
    dependencies=[Depends(require_owner_key)],
)


def _database_target() -> tuple[str, str] | None:
    """Return (provider, host) without ever returning credentials."""
    database_url = get_settings().database_url.strip()
    if not database_url.startswith(("postgres://", "postgresql://")):
        return None
    parsed = urlsplit(database_url)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    provider = "supabase" if "supabase" in host else "postgresql"
    return provider, host


def status() -> dict:
    target = _database_target()
    project_url = ( __import__("os").getenv("SUPABASE_URL") or "" ).strip()
    project_url_configured = project_url.startswith("https://") and "supabase" in project_url.lower()
    return {
        "integration": "supabase",
        "database_configured": target is not None,
        "database_provider": target[0] if target else None,
        "database_host_configured": bool(target),
        "project_url_configured": project_url_configured,
        "connection_tested": False,
        "migration_policy": "owner_approval_required",
        "credentials_exposed": False,
    }


def test_connection() -> dict:
    target = _database_target()
    if target is None:
        raise HTTPException(
            status_code=409,
            detail="AI_OS_DATABASE_URL is not configured for a valid PostgreSQL host.",
        )

    started = monotonic()
    try:
        # Supabase requires TLS. The short timeout prevents a hung dashboard request.
        with psycopg.connect(
            get_settings().database_url,
            connect_timeout=5,
            sslmode="require",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if not row or row[0] != 1:
                    raise RuntimeError("Database connectivity probe returned an unexpected result.")
    except Exception as exc:
        # Do not return exception text: drivers may include host, username or connection data.
        return {
            "integration": "supabase",
            "connected": False,
            "database_provider": target[0],
            "error_type": type(exc).__name__,
            "error": "Connection test failed. Verify the private Railway database URL, pooler mode, network access and SSL settings.",
            "credentials_exposed": False,
        }

    return {
        "integration": "supabase",
        "connected": True,
        "database_provider": target[0],
        "latency_ms": round((monotonic() - started) * 1000, 2),
        "probe": "SELECT 1",
        "schema_changed": False,
        "credentials_exposed": False,
    }


@router.get("/status")
def get_status():
    """Report configuration presence only; never reveal environment variable values."""
    return status()


@router.post("/test")
def post_test_connection():
    """Run a bounded, read-only connectivity probe; never run migrations or writes."""
    return test_connection()
