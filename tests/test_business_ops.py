from fastapi.testclient import TestClient

from ai_os.api import app


def test_business_records_distinguish_verified_revenue_and_pending_expenses():
    with TestClient(app) as client:
        customer = client.post("/business/customers", json={"title": "Sample buyer"})
        assert customer.status_code == 201
        assert customer.json()["record_type"] == "customer"

        expense = client.post("/business/expenses", json={
            "title": "Hosting invoice", "amount": 12.5, "currency": "USD"
        })
        assert expense.status_code == 201
        assert expense.json()["status"] == "awaiting_owner_approval"

        expected = client.post("/business/revenue", json={
            "title": "Unsigned order", "amount": 99, "currency": "USD"
        })
        assert expected.status_code == 201
        assert expected.json()["status"] == "unverified_not_counted"

        paid = client.post("/business/revenue", json={
            "title": "Verified sale", "amount": 25, "currency": "USD",
            "verified_payment": True
        })
        assert paid.status_code == 201
        assert paid.json()["status"] == "payment_verified"

        summary = client.get("/business/summary")
        assert summary.status_code == 200
        assert summary.json()["customers"] >= 1
        usd = next(x for x in summary.json()["verified_revenue_by_currency"] if x["currency"] == "USD")
        assert usd["total"] >= 25


def test_code_asset_license_offer_requires_ownership_and_dependency_review():
    with TestClient(app) as client:
        blocked = client.post("/code-assets", json={
            "name": "Unverified asset", "ownership_status": "unverified"
        })
        assert blocked.status_code == 201
        denied = client.post("/code-assets/license-offers", json={
            "asset_id": blocked.json()["id"], "buyer": "Potential buyer",
            "terms": "Draft non-exclusive license."
        })
        assert denied.status_code == 422

        asset = client.post("/code-assets", json={
            "name": "Original utility module",
            "repository_url": "https://github.com/example/project",
            "path": "src/utility.py",
            "ownership_status": "verified",
            "dependency_review": "passed",
            "license": "proprietary"
        })
        assert asset.status_code == 201
        offer = client.post("/code-assets/license-offers", json={
            "asset_id": asset.json()["id"], "buyer": "Potential buyer",
            "terms": "Draft non-exclusive license. No transfer until signed."
        })
        assert offer.status_code == 201
        assert offer.json()["status"] == "draft_pending_owner_approval"
        assert offer.json()["external_sharing"] is False
        approvals = client.get("/approvals")
        assert approvals.status_code == 200
        assert any(x["action"] == "review_code_license_offer" for x in approvals.json())
