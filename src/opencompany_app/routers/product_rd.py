"""Owner-authenticated Product & R&D workflow API and artifact delivery."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime
from opencompany_core.domain import AgentState, AuditRecord, TaskState, WorkItem
from opencompany_core.product_artifacts import generate_outpost_pack
from opencompany_core.product_rd import ProductRDError, ProductRDRepository, PRODUCT_STAGES


router = APIRouter(prefix="/product-rd", tags=["Product & R&D"],
                   dependencies=[Depends(require_owner_key)])
SYSTEM_STAGES = {"artifact_generation", "automated_qa"}
OWNER_STAGES = {"human_preview"}
MODEL_STAGES = set(PRODUCT_STAGES) - SYSTEM_STAGES - OWNER_STAGES


class ProductRDCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    brief: str = Field(min_length=1, max_length=12000)
    business_id: str = "digital-products"


class ProductRDStageCompleteInput(BaseModel):
    output: str = Field(min_length=1, max_length=12000)
    evidence: list[str] = Field(min_length=1, max_length=30)


class ProductRDOwnerReviewInput(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)


class ProductRDReworkInput(BaseModel):
    rationale: str = Field(min_length=1, max_length=2000)


def _repository(runtime: OpenCompanyRuntime) -> ProductRDRepository:
    return ProductRDRepository(runtime.store._connection, runtime.store._lock)


def _artifact_root() -> Path:
    return Path(os.environ.get("OPENCOMPANY_PRODUCT_ARTIFACT_ROOT", "data/product-artifacts")).expanduser()


def _call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ProductRDError as exc:
        message = str(exc)
        raise HTTPException(status_code=404 if "not found" in message.lower() else 409,
                            detail=message) from exc


@router.post("/workflows")
def create_product_workflow(payload: ProductRDCreateInput,
                            runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    workflow = _call(_repository(runtime).create, title=payload.title, brief=payload.brief,
                     business_id=payload.business_id)
    return {"workflow": workflow, "external_actions_enabled": False}


@router.get("/workflows")
def list_product_workflows(business_id: str | None = None, limit: int = 50,
                           runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    items = _call(_repository(runtime).list, business_id=business_id, limit=limit)
    return {"count": len(items), "workflows": items}


@router.get("/workflows/{workflow_id}")
def get_product_workflow(workflow_id: UUID,
                         runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    item = _repository(runtime).get(workflow_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product workflow not found.")
    return {"workflow": item}


@router.post("/workflows/{workflow_id}/delegate-stage")
def delegate_product_stage(workflow_id: UUID,
                           runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Create a normal, review-gated OpenCompany work item for the active stage."""
    repo = _repository(runtime)
    workflow = repo.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Product workflow not found.")
    stage = next((s for s in workflow["stages"] if s["status"] == "in_progress"), None)
    if stage is None or stage["key"] not in MODEL_STAGES:
        raise HTTPException(status_code=409, detail="The active stage is not an AI-delegable stage.")
    role_key = stage["owner_role"]
    agent = next((a for a in runtime.store.list_agents(limit=1000)
                  if a.role_key == role_key and a.state == AgentState.ACTIVE), None)
    if agent is None:
        raise HTTPException(status_code=409,
            detail=f"Required role {role_key} is not provisioned and ACTIVE. Provision and activate it before delegation.")
    if stage.get("work_item_id"):
        raise HTTPException(status_code=409, detail="This stage already has an assigned work item.")
    department = agent.department
    try:
        from opencompany_core.organization import default_organization
        spec = default_organization().get(department)
        if role_key not in spec.role_keys:
            raise LookupError("role is not part of its declared department")
    except LookupError as exc:
        raise HTTPException(status_code=409, detail="The assigned role does not match the canonical department catalogue.") from exc

    objective = (
        f"OpenCompany Product & R&D workflow {workflow_id}. Business unit: {workflow['business_id']}. "
        f"Stage: {stage['key']}. Product: {workflow['title']}. "
        f"Product brief: {workflow['brief']}. "
        "Produce an internal, evidence-backed stage deliverable only. "
        "Include method, findings, assumptions, acceptance criteria, limitations, and handoff. "
        "Do not create unsupported claims, contact customers, publish, purchase, spend, or change accounts. "
        "Use only confirmed zero-cost resources."
    )
    item = WorkItem(
        id=uuid4(), title=f"Product R&D · {stage['key']} · {workflow['title']}",
        objective=objective, department=department, state=TaskState.DRAFT,
        assigned_agent_id=agent.id, business_id=workflow["business_id"],
    )
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="product_rd.stage_work_item_created",
        subject_type="work_item", subject_id=str(item.id), outcome="draft",
        correlation_id=str(workflow_id),
        details={"workflow_id": str(workflow_id), "stage": stage["key"],
                 "business_id": workflow["business_id"], "agent_id": str(agent.id),
                 "role_key": role_key},
    )
    try:
        runtime.store.save_work_item_with_audit(item, event)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Could not persist stage work item: {type(exc).__name__}") from exc
    updated = _call(repo.attach_work_item, workflow_id, stage["key"], str(item.id))
    return {
        "workflow": updated, "work_item_id": str(item.id), "agent_id": str(agent.id),
        "role_key": role_key, "department": department, "work_item_state": "draft",
        "owner_must_mark_ready_enqueue_and_review": True,
        "execution_started": False,
    }


@router.post("/workflows/{workflow_id}/sync-stage")
def sync_product_stage(workflow_id: UUID,
                       runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Import only a completed, owner-reviewed OpenCompany deliverable into a stage."""
    repo = _repository(runtime)
    workflow = repo.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Product workflow not found.")
    stage = next((s for s in workflow["stages"] if s["status"] == "in_progress"), None)
    if stage is None or stage["key"] not in MODEL_STAGES:
        raise HTTPException(status_code=409, detail="The active stage is not an AI-delegable stage.")
    if not stage.get("work_item_id"):
        raise HTTPException(status_code=409, detail="Delegate the active stage before syncing its deliverable.")
    item = runtime.store.get_work_item(UUID(stage["work_item_id"]))
    if item is None or item.business_id != workflow["business_id"]:
        raise HTTPException(status_code=409, detail="Stage work item is missing or belongs to another business.")
    if item.state != TaskState.COMPLETED:
        raise HTTPException(status_code=409, detail="The stage work item must be completed through owner review first.")
    deliverables = runtime.store.list_deliverables(item.id)
    if not deliverables:
        raise HTTPException(status_code=409, detail="No persisted agent deliverable exists for this work item.")
    deliverable = deliverables[-1]
    evidence = [
        f"Owner-approved work item: {item.id}",
        f"Review-required deliverable: {deliverable['id']}",
        f"Provider/model: {deliverable['provider']}/{deliverable['model']}",
        f"Recorded inference cost: USD {float(deliverable['cost_usd']):.6f}",
    ]
    updated = _call(repo.complete_stage, workflow_id, stage["key"],
                    output=deliverable["content"][:12000], evidence=evidence,
                    artifact_refs=[f"work-item:{item.id}", f"deliverable:{deliverable['id']}"])
    return {"workflow": updated, "synced_deliverable_id": deliverable["id"],
            "external_actions_performed": False}


@router.post("/workflows/{workflow_id}/generate-pilot")
def generate_product_pilot(workflow_id: UUID,
                           runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    """Generate the internal OUTPOST SVG prototype and immediately run deterministic QA."""
    repo = _repository(runtime)
    workflow = repo.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Product workflow not found.")
    stage = next((s for s in workflow["stages"] if s["status"] == "in_progress"), None)
    if stage is None or stage["key"] != "artifact_generation":
        raise HTTPException(status_code=409, detail="Artifact generation is not the active stage.")
    if workflow["business_id"] != "digital-products":
        raise HTTPException(status_code=409, detail="The OUTPOST downloadable asset pilot belongs to digital-products.")
    if "outpost" not in workflow["title"].casefold():
        raise HTTPException(status_code=409, detail="This generator is reserved for the OUTPOST pilot workflow.")
    try:
        generated = generate_outpost_pack(str(workflow_id), _artifact_root())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=500, detail=f"Artifact generation failed safely: {type(exc).__name__}") from exc
    artifact_refs = [item["download_url"] for item in generated["artifacts"]]
    after_generation = _call(repo.complete_stage, workflow_id, "artifact_generation",
        output="Generated a deterministic original 30-icon SVG prototype, contact sheet, manifest, README, draft license notice, and ZIP archive.",
        evidence=[f"Generated {len(generated['artifacts'])} artifact files.",
                  "Generation used deterministic local code; no model call or external service was used."],
        artifact_refs=artifact_refs)
    qa = generated["qa"]
    after_qa = _call(repo.complete_stage, workflow_id, "automated_qa",
        output="Deterministic archive, manifest, file-count, and SVG-XML checks completed.",
        evidence=qa["passed_checks"] or ["QA checks returned no passed checks."],
        artifact_refs=artifact_refs, qa_result=qa)
    return {"workflow": after_qa, "generation": generated,
            "qa": qa, "human_preview_required": after_qa["stages"][5]["status"] == "in_progress",
            "external_actions_performed": False}


@router.get("/workflows/{workflow_id}/artifacts/{artifact_name}")
def download_product_artifact(workflow_id: UUID, artifact_name: str,
                              runtime: OpenCompanyRuntime = Depends(get_runtime)) -> FileResponse:
    workflow = _repository(runtime).get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Product workflow not found.")
    allowed = {"package.zip", "preview.svg", "manifest.json", "README.md", "LICENSE-DRAFT.txt"}
    if artifact_name not in allowed:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    root = _artifact_root().resolve()
    target = (root / str(workflow_id) / artifact_name).resolve()
    if target.parent != (root / str(workflow_id)).resolve() or not target.is_file() or target.is_symlink():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    media = "application/zip" if artifact_name.endswith(".zip") else (
        "image/svg+xml" if artifact_name.endswith(".svg") else "application/json" if artifact_name.endswith(".json") else "text/plain"
    )
    return FileResponse(target, media_type=media, filename=artifact_name)


@router.post("/workflows/{workflow_id}/stages/{stage_key}/complete")
def complete_product_stage(workflow_id: UUID, stage_key: str,
                           payload: ProductRDStageCompleteInput,
                           runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if stage_key not in OWNER_STAGES:
        raise HTTPException(status_code=409, detail="Only the human-preview checkpoint can be completed manually.")
    item = _call(_repository(runtime).complete_stage, workflow_id, stage_key,
                 output=payload.output, evidence=payload.evidence)
    return {"workflow": item}


@router.post("/workflows/{workflow_id}/return-to-production")
def return_product_to_production(workflow_id: UUID, payload: ProductRDReworkInput,
                                 runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    item = _call(_repository(runtime).return_to_production, workflow_id,
                 rationale=payload.rationale)
    return {"workflow": item}


@router.post("/workflows/{workflow_id}/owner-review")
def review_product_workflow(workflow_id: UUID, payload: ProductRDOwnerReviewInput,
                            runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    item = _call(_repository(runtime).owner_review, workflow_id,
                 approved=payload.approved, rationale=payload.rationale)
    return {"workflow": item, "published": False,
            "message": "Internal review only; no external action was performed."}
