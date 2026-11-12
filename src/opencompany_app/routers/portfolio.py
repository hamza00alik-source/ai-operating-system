"""Owner-controlled company-wide venture discovery and portfolio lifecycle."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.venture_portfolio import VenturePortfolio, VenturePortfolioError
from opencompany_app.api_schemas import VentureOpportunityInput, VentureOpportunityStatusInput
from opencompany_app.api_dependencies import get_runtime, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


router = APIRouter()


# Company-wide venture portfolio. This is intentionally distinct from operating
# business units: discovering an opportunity never creates a business or
# authorizes spending, publishing, customer contact, or a launch.
def _venture_portfolio(runtime: OpenCompanyRuntime) -> VenturePortfolio:
    return VenturePortfolio(runtime.store._connection, runtime.store._lock)


@router.get("/venture-opportunities", dependencies=[Depends(require_owner_key)])
def list_venture_opportunities(
    status: str | None = None,
    limit: int = 100,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        items = _venture_portfolio(runtime).list(status=status, limit=limit)
        return {"items": list(items), "count": len(items)}
    except VenturePortfolioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/venture-opportunities", dependencies=[Depends(require_owner_key)])
def create_venture_opportunity(
    payload: VentureOpportunityInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        item = _venture_portfolio(runtime).create(
            title=payload.title, slug=payload.slug, business_model=payload.business_model,
            description=payload.description, target_market=payload.target_market,
            evidence=payload.evidence,
        )
        return {"item": item, "message": "Opportunity saved in the company-wide portfolio; no business unit was created."}
    except VenturePortfolioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/venture-opportunities/{opportunity_id}/status", dependencies=[Depends(require_owner_key)])
def transition_venture_opportunity(
    opportunity_id: str,
    payload: VentureOpportunityStatusInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    try:
        item = _venture_portfolio(runtime).transition(
            opportunity_id, status=payload.status, rationale=payload.rationale,
            confirm_owner_approval=payload.confirm_owner_approval,
        )
    except VenturePortfolioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    return {"item": item, "message": "Status recorded. Launch approval does not provision accounts, spend money, or publish anything."}


@router.get("/venture-opportunities/{opportunity_id}/events", dependencies=[Depends(require_owner_key)])
def list_venture_opportunity_events(
    opportunity_id: str,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    portfolio = _venture_portfolio(runtime)
    if portfolio.get(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Venture opportunity not found.")
    return {"items": list(portfolio.events(opportunity_id))}

