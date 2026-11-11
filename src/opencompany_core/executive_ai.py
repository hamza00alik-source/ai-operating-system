"""CEO-level decomposition of owner objectives into draft department work items."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import uuid4

from .domain import TaskState, WorkItem
from .model_gateway import ModelGateway, ModelRequest
from .organization import default_organization
from .workforce import default_workforce


class ExecutivePlanningError(ValueError):
    pass


def _parse_model_json(text: str) -> dict:
    """Extract one JSON object from common model formatting without weakening schema checks."""
    if not isinstance(text, str) or not text.strip():
        raise ExecutivePlanningError("CEO model returned an empty response")
    candidate = text.lstrip("\ufeff").strip()
    fence = chr(96) * 3
    fenced = re.fullmatch(re.escape(fence) + r"(?:json)?\s*(.*?)\s*" + re.escape(fence),
                          candidate, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        if start < 0:
            raise ExecutivePlanningError("CEO model did not return a JSON object")
        try:
            payload, end = json.JSONDecoder().raw_decode(candidate[start:])
        except json.JSONDecodeError as exc:
            raise ExecutivePlanningError("CEO model did not return valid JSON") from exc
        if candidate[start + end:].strip():
            raise ExecutivePlanningError("CEO model returned extra content after its JSON object")
    if not isinstance(payload, dict):
        raise ExecutivePlanningError("CEO response must be a JSON object")
    return payload


@dataclass(frozen=True, slots=True)
class ExecutivePlan:
    rationale: str
    work_items: tuple[WorkItem, ...]
    provider: str
    model: str


def create_executive_plan(
    title: str,
    objective: str,
    gateway: ModelGateway,
    *,
    max_tasks: int = 10,
) -> ExecutivePlan:
    if not 1 <= max_tasks <= 10:
        raise ValueError("max_tasks must be between 1 and 10")
    departments = default_organization().all()
    department_context = [
        {"key": item.key, "name": item.name, "mission": item.mission}
        for item in departments
    ]
    ceo = default_workforce().get("chief_executive_orchestrator")
    ceo_steps = "\n".join(ceo.playbook.workflow_steps)
    prompt = (
        "OPENCOMPANY CHIEF EXECUTIVE WORK-PLANNING REQUEST\n"
        f"Executive role: {ceo.title}\n"
        f"Role mission: {ceo.mission}\n"
        f"CEO operating procedure:\n{ceo_steps}\n"
        f"Owner objective title: {title}\n"
        f"Owner objective: {objective}\n"
        f"Create between 1 and {max_tasks} practical department work items. "
        "Each task must have a single accountable department, a clear measurable objective, "
        "and dependencies expressed as zero-based indices of earlier tasks only. "
        "Do not invent department identifiers. Avoid assigning external actions or spending authority. "
        "Return exactly one valid JSON object and nothing else: no Markdown fences, no preamble, "
        "no commentary and no trailing text. Use double-quoted JSON keys and string values. "
        "The top-level object must have exactly these keys: rationale (string), work_items (array). "
        "Each work item must have exactly department (string), title (string), objective (string), "
        "depends_on (array of earlier integer indices).\\n"
        f"Departments: {json.dumps(department_context, separators=(',', ':'))}"
    )
    result = gateway.complete(
        ModelRequest(
            prompt=prompt, request_id=str(uuid4()), max_output_tokens=2400,
            work_item_id="executive-plan", role_key="chief_executive_orchestrator",
        ),
        request_budget_usd=0.0,
        preferred_provider="unorouter",
    )
    payload = _parse_model_json(result.text)
    if not isinstance(payload, dict) or set(payload) != {"rationale", "work_items"}:
        raise ExecutivePlanningError("CEO response must contain only rationale and work_items")
    rationale = payload["rationale"]
    raw_items = payload["work_items"]
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 2000:
        raise ExecutivePlanningError("CEO rationale must contain 1-2000 characters")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= max_tasks:
        raise ExecutivePlanningError("CEO must return between 1 and the configured maximum number of tasks")
    known_departments = {item.key for item in departments}
    ids = [uuid4() for _ in raw_items]
    items = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict) or set(raw) != {"department", "title", "objective", "depends_on"}:
            raise ExecutivePlanningError(f"CEO task {index} has an invalid shape")
        department = raw["department"]
        task_title = raw["title"]
        task_objective = raw["objective"]
        dependencies = raw["depends_on"]
        if department not in known_departments:
            raise ExecutivePlanningError(f"CEO selected unknown department: {department}")
        if not isinstance(task_title, str) or not 1 <= len(task_title.strip()) <= 240:
            raise ExecutivePlanningError(f"CEO task {index} has an invalid title")
        if not isinstance(task_objective, str) or not 1 <= len(task_objective.strip()) <= 12000:
            raise ExecutivePlanningError(f"CEO task {index} has an invalid objective")
        if not isinstance(dependencies, list) or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 or value >= index
            for value in dependencies
        ) or len(set(dependencies)) != len(dependencies):
            raise ExecutivePlanningError(f"CEO task {index} has invalid or forward dependencies")
        items.append(WorkItem(
            id=ids[index], title=task_title.strip(), objective=task_objective.strip(),
            department=department, state=TaskState.DRAFT,
            depends_on=tuple(ids[value] for value in dependencies),
        ))
    return ExecutivePlan(
        rationale=rationale.strip(), work_items=tuple(items),
        provider=result.provider, model=result.model,
    )
