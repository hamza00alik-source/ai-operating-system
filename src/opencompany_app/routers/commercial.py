"""Owner-controlled commercial opportunities, catalogue, quotes and orders."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_app.api_schemas import (
    CommercialOpportunityInput,
    CommercialProductStatusInput,
    CommercialProductInput,
    CommercialQuoteInput,
    CommercialQuoteDecisionInput,
    CommercialOrderStatusInput,
    CommercialOrderInput,
)
from opencompany_app.api_dependencies import get_store, require_owner_key


router = APIRouter()


@router.post("/commercial/opportunities", dependencies=[Depends(require_owner_key)])
def create_commercial_opportunity(
    payload: CommercialOpportunityInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    from datetime import datetime, timezone
    allowed = {"physical-agency", "physical-brand", "digital-products"}
    if payload.business_id not in allowed:
        raise HTTPException(status_code=422, detail="A customer opportunity must select exactly one commercial business unit; core is internal only.")
    if not payload.scope_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that this opportunity covers only the customer's stated need in the selected business.")
    now = datetime.now(timezone.utc).isoformat()
    opportunity_id = str(uuid4())
    record = {
        "id": opportunity_id, "business_id": payload.business_id,
        "customer_name": payload.customer_name.strip(),
        "customer_contact": payload.customer_contact.strip() if payload.customer_contact else None,
        "customer_need": payload.customer_need.strip(), "stage": "new",
        "created_at": now, "updated_at": now,
    }
    try:
        store.create_commercial_opportunity(record, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.opportunity_created",
            subject_type="commercial_opportunity", subject_id=opportunity_id,
            outcome="recorded", correlation_id=str(uuid4()),
            details={"business_id": payload.business_id, "scope_confirmed": True},
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"opportunity_id": opportunity_id, "business_id": payload.business_id, "stage": "new"}



@router.get("/commercial/opportunities", dependencies=[Depends(require_owner_key)])
def list_commercial_opportunities(
    business_id: str | None = None, store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        records = store.list_commercial_opportunities(business_id=business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(records), "opportunities": records}



@router.get("/commercial/opportunities/{opportunity_id}/catalogue", dependencies=[Depends(require_owner_key)])
def list_opportunity_catalogue(
    opportunity_id: UUID, store: SQLiteStore = Depends(get_store)
) -> dict:
    opportunity = store.get_commercial_opportunity(str(opportunity_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Commercial opportunity not found.")
    # The opportunity's immutable business_id is the only allowed catalogue scope.
    products = store.list_commercial_products(
        business_id=opportunity["business_id"], status="active"
    )
    return {
        "opportunity_id": str(opportunity_id),
        "business_id": opportunity["business_id"],
        "count": len(products),
        "products": products,
        "scope_enforced": True,
    }



@router.post("/commercial/products", dependencies=[Depends(require_owner_key)])
def create_commercial_product(
    payload: CommercialProductInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    from datetime import datetime, timezone
    allowed = {"physical-agency", "physical-brand", "digital-products"}
    if payload.business_id not in allowed:
        raise HTTPException(status_code=422, detail="Catalogue entries must belong to one commercial business unit; core is internal only.")
    now = datetime.now(timezone.utc).isoformat()
    product_id = str(uuid4())
    record = {
        "id": product_id, "business_id": payload.business_id,
        "name": payload.name.strip(), "description": payload.description.strip(),
        "category": payload.category.strip(), "status": "draft",
        "created_at": now, "updated_at": now,
    }
    try:
        store.create_commercial_product(record, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.product_created",
            subject_type="commercial_product", subject_id=product_id,
            outcome="draft", correlation_id=str(uuid4()),
            details={"business_id": payload.business_id, "status": "draft"},
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"product_id": product_id, "business_id": payload.business_id, "status": "draft", "published": False}



@router.post("/commercial/products/{product_id}/status", dependencies=[Depends(require_owner_key)])
def update_commercial_product_status(
    product_id: UUID, payload: CommercialProductStatusInput,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    from datetime import datetime, timezone
    if payload.status not in {"active", "archived"}:
        raise HTTPException(status_code=422, detail="Status must be active or archived.")
    if not payload.confirm_owner_approval:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to change catalogue status.")
    changed = store.update_commercial_product_status(
        str(product_id), payload.status, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner",
            action="commercial.product_status_changed",
            subject_type="commercial_product", subject_id=str(product_id),
            outcome=payload.status, correlation_id=str(uuid4()),
            details={"status": payload.status, "owner_confirmed": True},
        )
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Product not found or already archived.")
    return {"product_id": str(product_id), "status": payload.status, "published": False}



@router.get("/commercial/products", dependencies=[Depends(require_owner_key)])
def list_commercial_products(
    business_id: str | None = None, status: str | None = None,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        records = store.list_commercial_products(business_id=business_id, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(records), "products": records}



@router.post("/commercial/quotes", dependencies=[Depends(require_owner_key)])
def create_commercial_quote(
    payload: CommercialQuoteInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    currency = payload.currency.upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise HTTPException(status_code=422, detail="Currency must be a three-letter ISO code.")
    if payload.currency_exponent not in {0, 2, 3}:
        raise HTTPException(status_code=422, detail="Currency exponent must be 0, 2, or 3.")
    opportunity = store.get_commercial_opportunity(str(payload.opportunity_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Commercial opportunity not found.")
    subtotal = sum(item.quantity * item.unit_price_minor for item in payload.items)
    if subtotal <= 0 or subtotal > 9_000_000_000_000_000:
        raise HTTPException(status_code=422, detail="Quote total is outside the supported range.")
    now = datetime.now(timezone.utc).isoformat()
    quote_id = str(uuid4())
    record = {
        "id": quote_id, "opportunity_id": str(payload.opportunity_id),
        "business_id": opportunity["business_id"], "title": payload.title.strip(),
        "currency": currency, "currency_exponent": payload.currency_exponent,
        "subtotal_minor": subtotal, "terms": payload.terms.strip(),
        "created_at": now, "updated_at": now,
    }
    items = [{
        "id": str(uuid4()), "product_id": str(item.product_id),
        "description": item.description.strip(), "quantity": item.quantity,
        "unit_price_minor": item.unit_price_minor,
    } for item in payload.items]
    try:
        result = store.create_commercial_quote(record, items, AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.quote_created",
            subject_type="commercial_quote", subject_id=quote_id, outcome="draft",
            correlation_id=str(uuid4()),
            details={"business_id": opportunity["business_id"], "opportunity_id": str(payload.opportunity_id),
                     "currency": currency, "currency_exponent": payload.currency_exponent,
                     "subtotal_minor": subtotal},
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"quote_id": quote_id, **result, "sent": False}



@router.get("/commercial/quotes", dependencies=[Depends(require_owner_key)])
def list_commercial_quotes(
    opportunity_id: UUID | None = None, business_id: str | None = None,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        quotes = store.list_commercial_quotes(
            opportunity_id=str(opportunity_id) if opportunity_id else None,
            business_id=business_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(quotes), "quotes": quotes}



@router.post("/commercial/quotes/{quote_id}/decision", dependencies=[Depends(require_owner_key)])
def decide_commercial_quote(
    quote_id: UUID, payload: CommercialQuoteDecisionInput,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    if not payload.confirm_owner_decision:
        raise HTTPException(status_code=422, detail="Owner confirmation is required.")
    if payload.status not in {"approved_for_delivery", "accepted", "rejected", "void"}:
        raise HTTPException(status_code=422, detail="Unsupported quote decision.")
    if payload.status == "accepted" and not (payload.acceptance_reference and payload.acceptance_reference.strip()):
        raise HTTPException(status_code=422, detail="Record a customer acceptance evidence reference before marking accepted.")
    try:
        changed = store.update_commercial_quote_status(
            str(quote_id), payload.status, payload.acceptance_reference.strip() if payload.acceptance_reference else None,
            AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                actor_type="owner", actor_id="owner", action="commercial.quote_status_changed",
                subject_type="commercial_quote", subject_id=str(quote_id), outcome=payload.status,
                correlation_id=str(uuid4()),
                details={"status": payload.status, "owner_confirmed": True,
                         "acceptance_evidence_recorded": bool(payload.acceptance_reference)},
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="Quote not found.")
    return {"quote_id": str(quote_id), "status": payload.status, "sent": False}



@router.post("/commercial/orders", dependencies=[Depends(require_owner_key)])
def create_commercial_order(
    payload: CommercialOrderInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    if not payload.confirm_owner_order_record:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to create an order record.")
    order_id = str(uuid4())
    try:
        result = store.create_commercial_order(order_id, str(payload.quote_id), AuditRecord(
            id=uuid4(), occurred_at=datetime.now(timezone.utc),
            actor_type="owner", actor_id="owner", action="commercial.order_recorded",
            subject_type="commercial_order", subject_id=order_id, outcome="awaiting_owner_fulfilment",
            correlation_id=str(uuid4()), details={"quote_id": str(payload.quote_id), "owner_confirmed": True},
        ))
    except ValueError as exc:
        if "already exists for this quote" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="An order already exists for this quote.") from exc
        raise
    return result



@router.post("/commercial/orders/{order_id}/status", dependencies=[Depends(require_owner_key)])
def update_commercial_order_status(
    order_id: UUID, payload: CommercialOrderStatusInput,
    store: SQLiteStore = Depends(get_store)
) -> dict:
    if not payload.confirm_owner_status:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to update order status.")
    if payload.status not in {"in_progress", "fulfilled", "cancelled"}:
        raise HTTPException(status_code=422, detail="Unsupported order status.")
    try:
        changed = store.update_commercial_order_status(
            str(order_id), payload.status, AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                actor_type="owner", actor_id="owner", action="commercial.order_status_changed",
                subject_type="commercial_order", subject_id=str(order_id), outcome=payload.status,
                correlation_id=str(uuid4()),
                details={"status": payload.status, "owner_confirmed": True,
                         "external_fulfilment_triggered": False},
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="Order not found.")
    return {"order_id": str(order_id), "status": payload.status, "external_fulfilment_triggered": False}



@router.get("/commercial/orders", dependencies=[Depends(require_owner_key)])
def list_commercial_orders(
    business_id: str | None = None, store: SQLiteStore = Depends(get_store)
) -> dict:
    try:
        orders = store.list_commercial_orders(business_id=business_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(orders), "orders": orders}




"""Owner-controlled physical-business supplier records."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_app.api_schemas import CommercialSupplierInput, CommercialSupplierStatusInput
from opencompany_app.api_dependencies import get_store, require_owner_key


supplier_router = APIRouter()


@router.post("/commercial/suppliers", dependencies=[Depends(require_owner_key)])
def create_commercial_supplier(payload: CommercialSupplierInput, store: SQLiteStore = Depends(get_store)) -> dict:
    if payload.business_id not in {"physical-agency", "physical-brand"}:
        raise HTTPException(status_code=422, detail="Supplier records belong only to the physical-products agency or own-brand business.")
    relationship_type = "agency_supplier" if payload.business_id == "physical-agency" else "own_brand_supplier"
    now = datetime.now(timezone.utc)
    supplier_id = str(uuid4())
    record = {
        "id": supplier_id, "business_id": payload.business_id, "relationship_type": relationship_type,
        "name": payload.name.strip(), "contact_name": payload.contact_name, "email": payload.email,
        "phone": payload.phone, "country": payload.country,
        "product_categories": [value.strip() for value in payload.product_categories if value.strip()],
        "notes": payload.notes, "created_at": now.isoformat(), "updated_at": now.isoformat(),
    }
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="commercial.supplier_created", subject_type="commercial_supplier",
        subject_id=supplier_id, outcome="draft_saved", correlation_id=str(uuid4()),
        details={"business_id": payload.business_id, "relationship_type": relationship_type, "external_contact_made": False},
    )
    try:
        store.create_commercial_supplier(record, event)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"supplier_id": supplier_id, "business_id": payload.business_id,
            "relationship_type": relationship_type, "verification_status": "draft", "external_contact_made": False}



@router.get("/commercial/suppliers", dependencies=[Depends(require_owner_key)])
def list_commercial_suppliers(business_id: str | None = None, store: SQLiteStore = Depends(get_store)) -> dict:
    if business_id is not None and business_id not in {"physical-agency", "physical-brand"}:
        raise HTTPException(status_code=422, detail="Supplier records are available only for physical business units.")
    suppliers = store.list_commercial_suppliers(business_id=business_id)
    return {"count": len(suppliers), "suppliers": list(suppliers)}



@router.post("/commercial/suppliers/{supplier_id}/status", dependencies=[Depends(require_owner_key)])
def update_commercial_supplier_status(
    supplier_id: UUID, payload: CommercialSupplierStatusInput, store: SQLiteStore = Depends(get_store)
) -> dict:
    if payload.confirm_owner_decision is not True:
        raise HTTPException(status_code=422, detail="Owner confirmation is required to change supplier verification status.")
    if payload.status not in {"verified", "blocked"}:
        raise HTTPException(status_code=422, detail="Supplier status must be verified or blocked.")
    now = datetime.now(timezone.utc)
    event = AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="commercial.supplier_status_changed", subject_type="commercial_supplier",
        subject_id=str(supplier_id), outcome=payload.status, correlation_id=str(uuid4()),
        details={"verification_status": payload.status, "external_contact_made": False},
    )
    if not store.update_commercial_supplier_status(str(supplier_id), payload.status, event):
        raise HTTPException(status_code=404, detail="Supplier not found or already blocked.")
    return {"supplier_id": str(supplier_id), "status": payload.status,
            "external_contact_made": False, "purchase_or_commitment_created": False}


