"""Read-only provider information and owner executive execution portfolio."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import BUSINESS_UNIT_IDS, AgentState, TaskState
from opencompany_core.organization import default_organization
from opencompany_core.provider_catalog import free_provider_candidates
from opencompany_core.unorouter_adapter import unorouter_configuration_status
from opencompany_core.secret_vault import SecretVaultError
from opencompany_app.api_dependencies import get_optional_runtime, get_runtime, get_store, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime
from opencompany_core.persistence import SQLiteStore

provider_status_router = APIRouter()
provider_candidates_router = APIRouter()
executive_portfolio_router = APIRouter()


@provider_status_router.get("/providers/status")
def provider_runtime_status(runtime: OpenCompanyRuntime | None = Depends(get_optional_runtime)) -> dict:
    # Credentials are never returned. Saved owner settings take precedence over legacy env configuration.
    try:
        saved_uno = runtime.secret_vault.get("unorouter") if runtime is not None else None
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="Stored UnoRouter settings cannot be decrypted; check the server encryption key.") from exc
    uno = unorouter_configuration_status({
        "api_key": saved_uno["api_key"], "model": saved_uno["model"], "confirmed_free": "true"
    }) if saved_uno else unorouter_configuration_status()
    openrouter_key = os.environ.get("OPENCOMPANY_OPENROUTER_API_KEY", "").strip()
    openrouter_model = os.environ.get("OPENCOMPANY_OPENROUTER_FREE_MODEL", "").strip()
    openrouter_confirm = os.environ.get("OPENCOMPANY_CONFIRM_OPENROUTER_FREE", "").strip().lower()
    openrouter_configured = bool(
        openrouter_key and openrouter_model.endswith(":free") and openrouter_confirm == "true"
    )
    openrouter_partial = bool(openrouter_key or openrouter_model or openrouter_confirm) and not openrouter_configured
    providers = {
        "unorouter": uno,
        "openrouter": {
            "configured": openrouter_configured,
            "model": openrouter_model if openrouter_configured else None,
            "billing_mode": "free_confirmed" if openrouter_configured else "disabled",
            "partial_configuration_detected": openrouter_partial,
            "automatic_paid_fallback": False,
        },
    }
    active = next((name for name, state in providers.items() if state["configured"]), None)
    return {
        "gateway_enabled": active is not None,
        "provider": active,
        "model": providers[active]["model"] if active else None,
        "billing_mode": "free_confirmed" if active else "disabled",
        "providers": providers,
        "partial_configuration_detected": any(
            state["partial_configuration_detected"] for state in providers.values()
        ),
        "real_inference_verified": runtime.unorouter_tested_at is not None if runtime is not None else False,
        "paid_fallback": False,
    }


@provider_candidates_router.get("/providers/candidates")
def provider_candidates() -> dict:
    items = free_provider_candidates()
    uno_configured = unorouter_configuration_status()["configured"]
    return {
        "gateway_enabled": False,
        "count": len(items),
        "candidates": [
            {
                "key": item.key, "display_name": item.display_name,
                "access_mode": item.access_mode,
                "current_free_evidence": item.current_free_evidence,
                "limits_or_conditions": list(item.limits_or_conditions),
                "activation_gate": item.activation_gate,
                "configured": bool(uno_configured) if item.key == "unorouter-free-models" else False,
            }
            for item in items
        ],
    }


@executive_portfolio_router.get("/executive/portfolio", dependencies=[Depends(require_owner_key)])
def get_executive_portfolio(
    business_id: str | None = None,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    """Give the owner a company-wide view of CEO and department execution."""
    if business_id is not None and business_id not in BUSINESS_UNIT_IDS:
        raise HTTPException(status_code=422, detail="Unknown business unit.")

    profiles = store.list_agents(limit=1000)
    ceo = next((agent for agent in profiles
                if agent.role_key == "chief_executive_orchestrator"), None)
    work_items = store.list_work_items(business_id=business_id, limit=1000)
    department_rows: dict[str, dict] = {}
    items_payload = []
    for item in work_items:
        department = default_organization().get(item.department)
        manager = next((agent for agent in profiles
                        if agent.role_key == department.manager_role_key
                        and agent.department == item.department
                        and agent.team_key == "management"), None)
        dependencies = []
        for dependency_id in item.depends_on:
            dependency = store.get_work_item(dependency_id)
            if dependency is None:
                dependencies.append({
                    "work_item_id": str(dependency_id), "state": "missing",
                    "completed_with_deliverable": False,
                })
                continue
            if dependency.business_id != item.business_id:
                raise HTTPException(status_code=409, detail="Work dependency crossed a business boundary.")
            dependency_deliverables = store.list_deliverables(dependency_id)
            dependencies.append({
                "work_item_id": str(dependency_id), "state": dependency.state.value,
                "deliverable_count": len(dependency_deliverables),
                "completed_with_deliverable": (
                    dependency.state == TaskState.COMPLETED and bool(dependency_deliverables)
                ),
            })
        manager_ready = (
            item.state == TaskState.READY
            and bool(item.depends_on)
            and manager is not None
            and manager.state == AgentState.ACTIVE
            and item.assigned_agent_id == manager.id
            and all(value["completed_with_deliverable"] for value in dependencies)
        )
        deliverables = store.list_deliverables(item.id)
        row = {
            "id": str(item.id), "title": item.title, "objective": item.objective,
            "business_id": item.business_id, "department": item.department,
            "state": item.state.value,
            "assigned_agent_id": str(item.assigned_agent_id) if item.assigned_agent_id else None,
            "manager": ({
                "agent_id": str(manager.id), "role_key": manager.role_key,
                "state": manager.state.value,
            } if manager else None),
            "dependency_count": len(dependencies),
            "blocked_dependencies": [
                value["work_item_id"] for value in dependencies
                if not value["completed_with_deliverable"]
            ],
            "deliverable_count": len(deliverables),
            "manager_synthesis_ready": manager_ready,
        }
        items_payload.append(row)
        key = f"{item.business_id}:{item.department}"
        aggregate = department_rows.setdefault(key, {
            "business_id": item.business_id, "department": item.department,
            "work_item_count": 0, "states": {}, "blocked_count": 0,
            "review_count": 0, "completed_count": 0,
            "manager_synthesis_ready_count": 0,
        })
        aggregate["work_item_count"] += 1
        aggregate["states"][item.state.value] = aggregate["states"].get(item.state.value, 0) + 1
        aggregate["blocked_count"] += bool(row["blocked_dependencies"])
        aggregate["review_count"] += item.state == TaskState.REVIEW
        aggregate["completed_count"] += item.state == TaskState.COMPLETED
        aggregate["manager_synthesis_ready_count"] += manager_ready

    return {
        "platform": "opencompany-aios",
        "business_filter": business_id or "all",
        "ceo": ({
            "agent_id": str(ceo.id), "state": ceo.state.value,
            "active": ceo.state == AgentState.ACTIVE,
        } if ceo else None),
        "departments": list(department_rows.values()),
        "work_items": items_payload,
        "summary": {
            "work_item_count": len(items_payload),
            "department_count": len(department_rows),
            "blocked_work_item_count": sum(
                1 for item in items_payload if item["blocked_dependencies"]
            ),
            "awaiting_owner_review_count": sum(
                1 for item in items_payload if item["state"] == TaskState.REVIEW.value
            ),
            "completed_work_item_count": sum(
                1 for item in items_payload if item["state"] == TaskState.COMPLETED.value
            ),
            "manager_synthesis_ready_count": sum(
                1 for item in items_payload if item["manager_synthesis_ready"]
            ),
        },
        "execution_or_external_actions_performed": False,
    }
