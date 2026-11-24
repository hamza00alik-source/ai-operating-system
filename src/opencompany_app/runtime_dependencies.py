"""Process-local OpenCompany runtime and persistence dependencies."""
from __future__ import annotations

import os
from functools import lru_cache

from fastapi import HTTPException

from opencompany_core.persistence import SQLiteStore
from opencompany_core.delegation_records import DelegationRepository
from opencompany_app.runtime import OpenCompanyRuntime, create_runtime


@lru_cache(maxsize=1)
def _default_runtime() -> OpenCompanyRuntime:
    return create_runtime()


def get_runtime() -> OpenCompanyRuntime:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_runtime()


def get_optional_runtime() -> OpenCompanyRuntime | None:
    # Provider readiness is intentionally public and credential-free. Only
    # load owner-persisted settings when the owner runtime is configured.
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        return None
    return _default_runtime()


def get_delegation_store() -> DelegationRepository:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_runtime().delegations


def get_store() -> SQLiteStore:
    if not os.environ.get("OPENCOMPANY_OWNER_API_KEY"):
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    return _default_runtime().store
