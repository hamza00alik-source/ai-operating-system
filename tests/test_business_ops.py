from fastapi.testclient import TestClient

from ai_os.api import app


def test_business_records_distinguish_verified_revenue_and_pending_expenses(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(app) as client:
        customer = client.post("/business/customers", json={"title": "Sample buyer"}, headers=headers)
        assert customer.status_code == 201
        assert customer.json()["record_type"] == "customer"

        expense = client.post("/business/expenses", json={
            "title": "Hosting invoice", "amount": 12.5, "currency": "USD"
        }, headers=headers)
        assert expense.status_code == 201
        assert expense.json()["status"] == "awaiting_owner_approval"
        approval_id = expense.json()["approval_id"]
        assert approval_id
        decision = client.post(
            f"/approvals/{approval_id}/decision", json={"decision": "approved"}, headers=headers
        )
        assert decision.status_code == 200
        expenses = client.get("/business/expenses", headers=headers)
        linked_expense = next(x for x in expenses.json() if x["id"] == expense.json()["id"])
        assert linked_expense["status"] == "approved_for_manual_payment"

        expected = client.post("/business/revenue", json={
            "title": "Unsigned order", "amount": 99, "currency": "USD"
        }, headers=headers)
        assert expected.status_code == 201
        assert expected.json()["status"] == "unverified_not_counted"

        paid = client.post("/business/revenue", json={
            "title": "Verified sale", "amount": 25, "currency": "USD",
            "verified_payment": True
        }, headers=headers)
        assert paid.status_code == 201
        assert paid.json()["status"] == "payment_verified"

        summary = client.get("/business/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["customers"] >= 1
        usd = next(x for x in summary.json()["verified_revenue_by_currency"] if x["currency"] == "USD")
        assert usd["total"] >= 25


def test_code_asset_license_offer_requires_ownership_and_dependency_review(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(app) as client:
        blocked = client.post("/code-assets", json={
            "name": "Unverified asset", "ownership_status": "unverified"
        }, headers=headers)
        assert blocked.status_code == 201
        denied = client.post("/code-assets/license-offers", json={
            "asset_id": blocked.json()["id"], "buyer": "Potential buyer",
            "terms": "Draft non-exclusive license."
        }, headers=headers)
        assert denied.status_code == 422

        asset = client.post("/code-assets", json={
            "name": "Original utility module",
            "repository_url": "https://github.com/example/project",
            "path": "src/utility.py",
            "ownership_status": "verified",
            "dependency_review": "passed",
            "license": "proprietary"
        }, headers=headers)
        assert asset.status_code == 201
        offer = client.post("/code-assets/license-offers", json={
            "asset_id": asset.json()["id"], "buyer": "Potential buyer",
            "terms": "Draft non-exclusive license. No transfer until signed."
        }, headers=headers)
        assert offer.status_code == 201
        assert offer.json()["status"] == "draft_pending_owner_approval"
        assert offer.json()["external_sharing"] is False
        approvals = client.get("/approvals", headers=headers)
        assert approvals.status_code == 200
        assert any(x["action"] == "review_code_license_offer" for x in approvals.json())
