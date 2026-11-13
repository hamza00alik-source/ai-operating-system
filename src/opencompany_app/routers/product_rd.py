"""Owner-authenticated Product & R&D workflow API."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime
from opencompany_core.product_rd import ProductRDError, ProductRDRepository


router = APIRouter(prefix="/product-rd", tags=["Product & R&D"],
                   dependencies=[Depends(require_owner_key)])


class ProductRDCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    brief: str = Field(min_length=1, max_length=12000)
    business_id: str = "digital-products"


class ProductRDStageCompleteInput(BaseModel):
    output: str = Field(min_length=1, max_length=12000)
    evidence: list[str] = Field(min_length=1, max_length=30)
    artifact_refs: list[str] = Field(default_factory=list, max_length=30)
    qa_result: dict | None = None


class ProductRDOwnerReviewInput(BaseModel):
    approved: bool
    rationale: str = Field(min_length=1, max_length=2000)


class ProductRDReworkInput(BaseModel):
    rationale: str = Field(min_length=1, max_length=2000)


def _repository(runtime: OpenCompanyRuntime) -> ProductRDRepository:
    return ProductRDRepository(runtime.store._connection, runtime.store._lock)


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


@router.post("/workflows/{workflow_id}/stages/{stage_key}/complete")
def complete_product_stage(workflow_id: UUID, stage_key: str,
                           payload: ProductRDStageCompleteInput,
                           runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    item = _call(_repository(runtime).complete_stage, workflow_id, stage_key,
                 output=payload.output, evidence=payload.evidence,
                 artifact_refs=payload.artifact_refs, qa_result=payload.qa_result)
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
