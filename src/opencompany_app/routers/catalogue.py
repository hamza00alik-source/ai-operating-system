"""Read-only company catalogue and capability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from opencompany_core.workforce import default_workforce
from opencompany_core.organization import default_organization
from opencompany_core.media_studio import video_capabilities
from opencompany_app.api_schemas import WorkforceRoutePreviewInput


router = APIRouter()


@router.get("/workforce/roles")
def workforce_roles() -> dict:
    roles = default_workforce().all()
    return {
        "catalogue": "opencompany-original",
        "count": len(roles),
        "specialist_count": sum(1 for role in roles if "__" in role.key),
        "leadership_role_count": sum(1 for role in roles if "__" not in role.key),
        "team_count": len({role.team_key for role in roles if "__" in role.key}),
        "roles": [
            {
                "key": role.key, "title": role.title, "function": role.function, "team_key": role.team_key,
                "mission": role.mission, "capabilities": list(role.capabilities),
                "permitted_outputs": list(role.permitted_outputs),
                "prohibited_actions": list(role.prohibited_actions),
                "playbook": {
                    "intake_requirements": list(role.playbook.intake_requirements),
                    "workflow_steps": list(role.playbook.workflow_steps),
                    "deliverable_contract": list(role.playbook.deliverable_contract),
                    "quality_rubric": list(role.playbook.quality_rubric),
                    "escalation_triggers": list(role.playbook.escalation_triggers),
                    "tool_scopes": list(role.playbook.tool_scopes),
                },
            }
            for role in roles
        ],
    }


@router.post("/workforce/route-preview")
def workforce_route_preview(payload: WorkforceRoutePreviewInput) -> dict:
    try:
        default_organization().get(payload.department)
        matches = default_workforce().match_in_department(
            payload.department, payload.required_capabilities
        )[:payload.limit]
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    requested = {value.strip().casefold() for value in payload.required_capabilities}
    return {
        "department": payload.department,
        "required_capabilities": payload.required_capabilities,
        "candidate_count": len(matches),
        "candidates": [
            {
                "role_key": role.key,
                "title": role.title,
                "team_key": role.team_key,
                "matched_capabilities": [
                    capability for capability in role.capabilities
                    if capability.casefold() in requested
                ],
                "capabilities": list(role.capabilities),
            }
            for role in matches
        ],
        "assignment_performed": False,
        "execution_started": False,
    }


@router.get("/organization/departments")
def organization_departments() -> dict:
    departments = default_organization().all()
    return {
        "catalogue": "opencompany-original",
        "count": len(departments),
        "departments": [
            {
                "key": item.key, "name": item.name, "mission": item.mission,
                "accountabilities": list(item.accountabilities),
                "manager_role_key": item.manager_role_key,
                "role_keys": list(item.role_keys),
                "decision_scope": list(item.decision_scope),
                "success_measures": list(item.success_measures),
                "approval_boundaries": list(item.approval_boundaries),
            }
            for item in departments
        ],
    }


@router.get("/media/capabilities")
def media_capabilities() -> dict:
    items = video_capabilities()
    return {
        "count": len(items),
        "capabilities": [
            {
                "key": item.key, "display_name": item.display_name,
                "state": item.state.value,
                "generation_modes": list(item.generation_modes),
                "execution_requirements": list(item.execution_requirements),
                "zero_budget_path": item.zero_budget_path,
                "safety_controls": list(item.safety_controls),
            }
            for item in items
        ],
    }
