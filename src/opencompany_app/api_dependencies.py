"""Shared runtime, persistence and owner-authentication dependencies.

This module owns the cached runtime singleton so API startup, shutdown and
route dependencies all continue to use the same process-local instance.
"""
from __future__ import annotations

import hmac
import os
import time
from functools import lru_cache
from threading import Lock
from urllib.parse import urlsplit

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Cookie, Depends, Header, HTTPException, Request

from opencompany_core.domain import AgentState, AuditRecord, WorkItem
from opencompany_core.persistence import SQLiteStore
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.organization import default_organization
from opencompany_core.workforce import default_workforce
from opencompany_core.worker_queue import QueueError
from opencompany_app.runtime import OpenCompanyRuntime, create_runtime


_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_LOCK = Lock()
_LOGIN_WINDOW_SECONDS = 900
_LOGIN_MAX_FAILURES = 5
_LOGIN_MAX_TRACKED_CLIENTS = 10_000

def _login_retry_after(client_key: str, *, failed: bool = False) -> int:
    now = time.monotonic()
    with _LOGIN_LOCK:
        for key, attempts in list(_LOGIN_FAILURES.items()):
            fresh = [stamp for stamp in attempts if now - stamp < _LOGIN_WINDOW_SECONDS]
            if fresh:
                _LOGIN_FAILURES[key] = fresh
            else:
                _LOGIN_FAILURES.pop(key, None)
        if client_key not in _LOGIN_FAILURES and len(_LOGIN_FAILURES) >= _LOGIN_MAX_TRACKED_CLIENTS:
            oldest_key = min(
                _LOGIN_FAILURES,
                key=lambda key: _LOGIN_FAILURES[key][-1] if _LOGIN_FAILURES[key] else now,
            )
            _LOGIN_FAILURES.pop(oldest_key, None)
        attempts = _LOGIN_FAILURES.setdefault(client_key, [])
        if failed:
            attempts.append(now)
        if len(attempts) < _LOGIN_MAX_FAILURES:
            return 0
        return max(1, int(_LOGIN_WINDOW_SECONDS - (now - attempts[0])))

def _clear_login_failures(client_key: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.pop(client_key, None)

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


def require_owner_key(
    request: Request,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    x_opencompany_api_key: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
    opencompany_session: str | None = Cookie(default=None),
) -> str:
    expected = os.environ.get("OPENCOMPANY_OWNER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner API authentication is not configured.")
    if opencompany_session:
        mutating = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
        if runtime.sessions.validate(
            opencompany_session, x_csrf_token, require_csrf=mutating
        ):
            # Browser sessions are same-origin only. SameSite cookies and a
            # session-bound CSRF token are required, and Origin must match Host.
            # API-key clients remain available for explicit server-to-server use.
            if mutating:
                origin = request.headers.get("origin")
                host = request.headers.get("host", "").casefold()
                try:
                    origin_parts = urlsplit(origin or "")
                    origin_host = origin_parts.netloc.casefold()
                    valid_origin = (
                        origin_parts.scheme in {"http", "https"}
                        and bool(origin_host)
                        and origin_host == host
                        and origin_parts.path in {"", "/"}
                        and not origin_parts.query
                        and not origin_parts.fragment
                    )
                except ValueError:
                    valid_origin = False
                if not valid_origin:
                    raise HTTPException(status_code=403, detail="Owner session requests must use the same origin.")
            return "owner"
    client_key = request.client.host if request.client else "unknown"
    if x_opencompany_api_key and hmac.compare_digest(x_opencompany_api_key, expected):
        _clear_login_failures(client_key)
        return "owner"
    if x_opencompany_api_key:
        retry_after = _login_retry_after(client_key, failed=True)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Too many failed owner authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    raise HTTPException(status_code=401, detail="Owner authentication failed.")


def work_item_audit_record(item: WorkItem, action: str) -> AuditRecord:
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner", action=action,
        subject_type="work_item", subject_id=str(item.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={
            "state": item.state.value, "department": item.department,
            "business_id": item.business_id,
        },
    )

def _auto_queue_approved_work_enabled() -> bool:
    return os.environ.get("OPENCOMPANY_AUTO_QUEUE_APPROVED_WORK", "false").strip().casefold() in {"1", "true", "yes", "on"}


def _free_provider_ready(runtime: OpenCompanyRuntime) -> bool:
    return bool(runtime.gateway.eligible_providers(request_budget_usd=0.0))


def _auto_queue_task(runtime: OpenCompanyRuntime, task: WorkItem, agent, *, action: str) -> None:
    from datetime import datetime, timezone

    if agent is None or agent.state != AgentState.ACTIVE or agent.department != task.department:
        raise QueueError("automatic queueing requires an active assignee in the task department")
    department = default_organization().get(task.department)
    role = default_workforce().get(agent.role_key)
    expected_team = (
        "executive" if agent.role_key == "chief_executive_orchestrator"
        else "management" if agent.role_key == department.manager_role_key
        else role.team_key
    )
    if agent.role_key not in department.role_keys or agent.team_key != expected_team:
        raise QueueError("automatic queueing rejected an unverified role/team assignment")
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="system", actor_id="opencompany-auto-queue",
        action=action, subject_type="work_item", subject_id=str(task.id),
        outcome="recorded", correlation_id=str(uuid4()),
        details={"agent_id": str(agent.id), "role_key": agent.role_key,
                 "team_key": agent.team_key, "business_id": task.business_id,
                 "request_budget_usd": 0.0},
    )
    runtime.queue.enqueue_authorized(
        task, agent.id, {"role_key": agent.role_key, "team_key": agent.team_key}, event,
    )

