"""Read-only owner reporting over evidence-backed revenue records.

This module intentionally reports confirmed gross receipts only. Fees, refunds,
expenses, and net profit remain unavailable until separately evidenced.
"""
from __future__ import annotations

BUSINESS_LINES = (
    "physical_agency",
    "own_physical_brand",
    "digital_products",
)


class RevenueDashboard:
    """Build a read-only revenue overview without mixing business lines/currencies."""

    def __init__(self, store):
        self.store = store

    def snapshot(self, *, currencies=("USD", "EUR", "PKR")):
        normalized = []
        for currency in currencies:
            if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
                raise ValueError("Currencies must be three-letter codes")
            code = currency.upper()
            if code not in normalized:
                normalized.append(code)

        lines = []
        for business_line in BUSINESS_LINES:
            reports = [
                self.store.revenue_totals(business_line=business_line, currency=currency)
                for currency in normalized
            ]
            lines.append({
                "business_line": business_line,
                "currencies": reports,
            })

        all_orders = self.store.list_sale_evidence()
        pending = [item for item in all_orders if not item.get("received", False)]
        unclassified = [
            item for item in all_orders
            if item.get("business_line", "unclassified") == "unclassified"
        ]
        return {
            "report_type": "evidence_backed_revenue",
            "business_lines": lines,
            "pending_order_count": len(pending),
            "unclassified_order_count": len(unclassified),
            "fees": None,
            "refunds": None,
            "expenses": None,
            "net_profit": None,
            "limitations": [
                "Only explicitly confirmed receipts are included in gross_received.",
                "Currencies and business lines are reported separately.",
                "Pending and unclassified orders are excluded from received totals.",
                "Fees, refunds, expenses, and net profit are not yet tracked.",
            ],
        }
