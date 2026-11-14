from datetime import datetime, timezone
import sqlite3
from uuid import uuid4

import pytest

from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore


def _event(business_id, event_type, source_reference, amount_minor=10000):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "business_id": business_id,
        "order_id": None,
        "event_type": event_type,
        "amount_minor": amount_minor,
        "currency": "USD",
        "source_reference": source_reference,
        "evidence_reference": "owner-checked-statement:line-12",
        "note": "synthetic test evidence",
        "occurred_at": now,
    }


def _audit(subject_id):
    return AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner",
        action="commercial.financial_event_recorded",
        subject_type="commercial_financial_event", subject_id=subject_id,
        outcome="owner_verified_reference_recorded", correlation_id=str(uuid4()),
        details={"owner_verified": True, "payment_initiated": False},
    )


def test_financial_ledger_separates_agency_commission_from_supplier_value(tmp_path):
    store = SQLiteStore(tmp_path / "finance.sqlite3")
    commission = _event("physical-agency", "agency_commission", "agency-invoice-001", 2500)
    payable = _event("physical-agency", "supplier_payable", "supplier-invoice-001", 20000)
    cash = _event("physical-agency", "payment_received", "settlement-001", 20000)

    store.record_financial_event(commission, _audit(commission["id"]))
    store.record_financial_event(payable, _audit(payable["id"]))
    store.record_financial_event(cash, _audit(cash["id"]))

    summary = store.financial_summary(business_id="physical-agency")
    assert len(summary) == 1
    assert summary[0]["recognized_revenue_minor"] == 2500
    assert summary[0]["operating_costs_minor"] == 20000
    assert summary[0]["cash_received_minor"] == 20000
    assert summary[0]["net_contribution_minor"] == -17500
    assert summary[0]["revenue_basis"] == "agency commission only"
    assert summary[0]["fx_conversion_performed"] is False
    store.close()


def test_financial_ledger_keeps_business_and_currency_totals_separate(tmp_path):
    store = SQLiteStore(tmp_path / "finance-scope.sqlite3")
    own_brand = _event("physical-brand", "sales_revenue", "brand-sale-1", 15000)
    digital = _event("digital-products", "sales_revenue", "digital-sale-1", 5000)
    store.record_financial_event(own_brand, _audit(own_brand["id"]))
    store.record_financial_event(digital, _audit(digital["id"]))

    summaries = store.financial_summary()
    assert {(row["business_id"], row["currency"]) for row in summaries} == {
        ("physical-brand", "USD"), ("digital-products", "USD")
    }
    assert {row["recognized_revenue_minor"] for row in summaries} == {5000, 15000}
    assert store.list_financial_events(business_id="physical-agency") == ()
    store.close()


def test_financial_ledger_rejects_duplicate_source_reference_and_cross_business_order(tmp_path):
    store = SQLiteStore(tmp_path / "finance-idempotency.sqlite3")
    first = _event("digital-products", "sales_revenue", "platform-order-42")
    store.record_financial_event(first, _audit(first["id"]))
    duplicate = _event("digital-products", "sales_revenue", "platform-order-42")
    with pytest.raises(sqlite3.IntegrityError):
        store.record_financial_event(duplicate, _audit(duplicate["id"]))

    mismatched = _event("physical-agency", "agency_commission", "agency-order-1")
    mismatched["order_id"] = str(uuid4())
    with pytest.raises(ValueError, match="does not belong"):
        store.record_financial_event(mismatched, _audit(mismatched["id"]))
    store.close()
