"""Owner-authenticated API for the Product & R&D workflow."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from opencompany_core.product_workflow import ProductWorkflowError, ProductWorkflowRepository


def _runtime_for_request(request: Request):
    # Resolve lazily to avoid an import cycle and respect FastAPI test overrides.
    from opencompany_app.api import get_runtime

    runtime_factory = request.app.dependency_overrides.get(get_runtime, get_runtime)
    return runtime_factory()


def owner_guard(request: Request) -> str:
    # Resolve the canonical API guard lazily to avoid an import cycle.
    from opencompany_app.api import require_owner_key

    runtime = _runtime_for_request(request)
    return require_owner_key(
        request,
        runtime,
        request.headers.get("x-opencompany-api-key"),
        request.headers.get("x-csrf-token"),
        request.cookies.get("opencompany_session"),
    )


def repository(request: Request) -> ProductWorkflowRepository:
    runtime = _runtime_for_request(request)
    return ProductWorkflowRepository(runtime.store._connection, runtime.store._lock)


class ProductWorkflowCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    brief: str = Field(min_length=1, max_length=12000)


class ProductStageComplete(BaseModel):
    output: str = Field(min_length=1, max_length=12000)
    artifact_refs: list[str] = Field(default_factory=list, max_length=30)
    evidence: list[str] = Field(default_factory=list, max_length=30)
    qa_result: dict | None = None


class ProductStageBlock(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ProductOwnerReview(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)


router = APIRouter(prefix="/product-workflows", tags=["Product & R&D"], dependencies=[Depends(owner_guard)])


def _run(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ProductWorkflowError as exc:
        message = str(exc)
        code = 404 if "not found" in message.lower() else 409
        raise HTTPException(status_code=code, detail=message) from exc


@router.post("")
def create_product_workflow(payload: ProductWorkflowCreate, request: Request) -> dict:
    """Create an internal zero-budget production workflow; no external actions."""
    return _run(repository(request).create, payload.title, payload.brief)


@router.get("")
def list_product_workflows(request: Request, limit: int = 50) -> dict:
    items = _run(repository(request).list, limit)
    return {"count": len(items), "workflows": items}


@router.get("/{workflow_id}")
def get_product_workflow(workflow_id: UUID, request: Request) -> dict:
    item = repository(request).get(workflow_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product workflow not found.")
    return item


@router.post("/{workflow_id}/stages/{stage_key}/start")
def start_product_stage(workflow_id: UUID, stage_key: str, request: Request) -> dict:
    return _run(repository(request).start_stage, workflow_id, stage_key)


@router.post("/{workflow_id}/stages/{stage_key}/complete")
def complete_product_stage(workflow_id: UUID, stage_key: str, payload: ProductStageComplete, request: Request) -> dict:
    return _run(
        repository(request).complete_stage, workflow_id, stage_key,
        output=payload.output, artifact_refs=payload.artifact_refs, evidence=payload.evidence,
        qa_result=payload.qa_result,
    )


@router.post("/{workflow_id}/stages/{stage_key}/block")
def block_product_stage(workflow_id: UUID, stage_key: str, payload: ProductStageBlock, request: Request) -> dict:
    return _run(repository(request).block_stage, workflow_id, stage_key, payload.reason)


@router.post("/{workflow_id}/return-to-production")
def return_product_to_production(workflow_id: UUID, payload: ProductStageBlock, request: Request) -> dict:
    return _run(repository(request).return_to_production, workflow_id, payload.reason)


@router.post("/{workflow_id}/owner-review")
def review_product_workflow(workflow_id: UUID, payload: ProductOwnerReview, request: Request) -> dict:
    return _run(
        repository(request).owner_review, workflow_id,
        approved=payload.approved, rationale=payload.rationale,
    )
