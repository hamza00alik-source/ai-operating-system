"""Model-assisted department-manager planning with deterministic role validation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from .domain import WorkItem
from .manager_orchestration import ManagerDelegationPlan, plan_department_work
from .model_gateway import ModelGateway, ModelRequest
from .organization import default_organization
from .workforce import default_workforce, specialist_role_keys


class ManagerPlanningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ManagerRecommendation:
    required_capabilities: tuple[str, ...]
    rationale: str
    provider: str
    model: str
    plan: ManagerDelegationPlan


def recommend_department_plan(
    item: WorkItem,
    gateway: ModelGateway,
    *,
    max_specialists: int = 15,
) -> ManagerRecommendation:
    """Ask the manager model to select exact catalogue capabilities, then validate locally."""
    if not 1 <= max_specialists <= 50:
        raise ValueError("max_specialists must be between 1 and 50")
    department = default_organization().get(item.department)
    workforce = default_workforce()
    manager = workforce.get(department.manager_role_key)
    roles = tuple(workforce.get(key) for key in specialist_role_keys(item.department))
    allowed = sorted({
        capability
        for role in (manager, *roles)
        for capability in role.capabilities
    })
    manager_steps = "\n".join(manager.playbook.workflow_steps)
    prompt = (
        "OPENCOMPANY DEPARTMENT MANAGER PLANNING REQUEST\n"
        f"Manager role: {manager.title}\n"
        f"Department mission: {department.mission}\n"
        f"Manager operating procedure:\n{manager_steps}\n"
        f"Business unit: {item.business_id}. Keep all context inside this business unit.\n"
        f"Work item title: {item.title}\n"
        f"Work item objective: {item.objective}\n"
        "Select the smallest useful set of exact capability identifiers from the allowed catalogue. "
        "Do not invent identifiers. Consider dependencies, evidence, risks and which specialist team "
        "can deliver the requested outcome. Return only one JSON object with keys "
        "required_capabilities (array of 1 to 8 exact strings) and rationale (string up to 1000 chars).\n"
        f"Allowed capability identifiers: {json.dumps(allowed, separators=(',', ':'))}"
    )
    result = gateway.complete(
        ModelRequest(
            prompt=prompt, request_id=str(uuid4()), max_output_tokens=900,
            work_item_id=str(item.id), role_key=manager.key,
            business_id=item.business_id,
        ),
        request_budget_usd=0.0,
        preferred_provider="unorouter",
    )
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise ManagerPlanningError("manager model did not return valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"required_capabilities", "rationale"}:
        raise ManagerPlanningError("manager model response must contain only required_capabilities and rationale")
    capabilities = payload["required_capabilities"]
    rationale = payload["rationale"]
    if (
        not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 8
        or any(not isinstance(value, str) or value not in allowed for value in capabilities)
        or len(set(capabilities)) != len(capabilities)
    ):
        raise ManagerPlanningError("manager selected invalid or duplicate capability identifiers")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 1000:
        raise ManagerPlanningError("manager rationale must contain 1-1000 characters")
    plan = plan_department_work(item, capabilities, max_specialists=max_specialists)
    return ManagerRecommendation(
        required_capabilities=tuple(capabilities),
        rationale=rationale.strip(),
        provider=result.provider,
        model=result.model,
        plan=plan,
    )
