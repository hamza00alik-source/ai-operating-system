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


def test_payout_reconciliation_preview_matches_exact_lines_without_persisting(tmp_path):
    store = SQLiteStore(tmp_path / "payout-preview.sqlite3")
    first = _event("digital-products", "sales_revenue", "platform-order-100", 1200)
    second = _event("digital-products", "platform_fee", "platform-fee-100", 200)
    store.record_financial_event(first, _audit(first["id"]))
    store.record_financial_event(second, _audit(second["id"]))

    result = store.preview_payout_reconciliation(
        business_id="digital-products", currency="USD",
        payout_reference="payout-batch-9",
        lines=[
            {"source_reference": "platform-order-100", "amount_minor": 1200},
            {"source_reference": "platform-fee-100", "amount_minor": 200},
            {"source_reference": "missing-order", "amount_minor": 500},
            {"source_reference": "platform-order-100", "amount_minor": 1200},
        ],
    )
    assert result["matched_count"] == 2
    assert result["unmatched_count"] == 2
    assert result["fully_matched"] is False
    assert result["statement_lines_total_minor"] == 3100
    assert result["matched_lines_total_minor"] == 1400
    assert result["lines"][2]["status"] == "unmatched"
    assert result["lines"][3]["status"] == "duplicate_statement_reference"
    assert result["persisted"] is False
    assert result["payment_or_payout_action_performed"] is False
    assert len(store.list_financial_events(business_id="digital-products")) == 2
    store.close()


def test_payout_reconciliation_preview_flags_amount_mismatch_and_business_isolation(tmp_path):
    store = SQLiteStore(tmp_path / "payout-mismatch.sqlite3")
    event = _event("physical-brand", "sales_revenue", "brand-order-7", 999)
    store.record_financial_event(event, _audit(event["id"]))
    result = store.preview_payout_reconciliation(
        business_id="physical-brand", currency="USD", payout_reference="brand-payout-7",
        lines=[{"source_reference": "brand-order-7", "amount_minor": 1000}],
    )
    assert result["lines"][0]["status"] == "amount_mismatch"
    assert result["fully_matched"] is False
    assert store.preview_payout_reconciliation(
        business_id="digital-products", currency="USD", payout_reference="other-payout",
        lines=[{"source_reference": "brand-order-7", "amount_minor": 999}],
    )["lines"][0]["status"] == "unmatched"
    with pytest.raises(ValueError, match="between 1 and 500"):
        store.preview_payout_reconciliation(
            business_id="physical-brand", currency="USD", payout_reference="empty", lines=[]
        )
    store.close()
