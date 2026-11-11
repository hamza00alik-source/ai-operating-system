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

        pending_expense = client.post("/business/expenses", json={
            "title": "Unapproved invoice", "amount": 7, "currency": "USD"
        }, headers=headers)
        assert pending_expense.status_code == 201
        premature = client.post(
            f"/business/expenses/{pending_expense.json()['id']}/confirm-paid?business_id=core",
            json={}, headers=headers
        )
        assert premature.status_code == 409

        confirmed_paid = client.post(
            f"/business/expenses/{expense.json()['id']}/confirm-paid?business_id=core",
            json={}, headers=headers
        )
        assert confirmed_paid.status_code == 200
        assert confirmed_paid.json()["status"] == "owner_confirmed_paid"
        assert confirmed_paid.json()["paid_at"]
        repeated = client.post(
            f"/business/expenses/{expense.json()['id']}/confirm-paid?business_id=core",
            json={}, headers=headers
        )
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "owner_confirmed_paid"

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
        paid_usd = next(x for x in summary.json()["owner_confirmed_paid_expenses_by_currency"] if x["currency"] == "USD")
        assert paid_usd["total"] >= 12.5
        net_usd = next(x for x in summary.json()["verified_net_cash_movement_mtd_by_currency"] if x["currency"] == "USD")
        assert net_usd["owner_confirmed_paid_expenses"] > 0
        assert net_usd["net_cash_movement"] == round(
            net_usd["verified_revenue"] - net_usd["owner_confirmed_paid_expenses"], 2
        )
        assert summary.json()["expenses_approved_awaiting_manual_payment"] == 0


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



def test_investor_relationship_management(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(app) as client:
        created = client.post("/business/investors", headers=headers, json={
            "name": "Example Capital", "organization": "Example Ventures",
            "contact": "partner@example.test", "stage": "interested",
            "notes": "Initial inbound interest."
        })
        assert created.status_code == 201
        assert created.json()["stage"] == "interested"
        listing = client.get("/business/investors", headers=headers)
        assert listing.status_code == 200
        assert any(x["id"] == created.json()["id"] for x in listing.json())



def test_code_assets_and_license_offers_are_business_isolated(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(app) as client:
        asset = client.post("/code-assets", headers=headers, json={
            "business_id": "digital-products",
            "name": "Digital product source",
            "ownership_status": "verified",
            "dependency_review": "passed",
        })
        assert asset.status_code == 201
        assert asset.json()["business_id"] == "digital-products"
        digital_assets = client.get("/code-assets?business_id=digital-products", headers=headers)
        agency_assets = client.get("/code-assets?business_id=physical-agency", headers=headers)
        assert any(item["id"] == asset.json()["id"] for item in digital_assets.json())
        assert all(item["id"] != asset.json()["id"] for item in agency_assets.json())

        cross_business_offer = client.post("/code-assets/license-offers", headers=headers, json={
            "business_id": "physical-agency", "asset_id": asset.json()["id"],
            "buyer": "Agency buyer", "terms": "Draft offer only.",
        })
        assert cross_business_offer.status_code == 404
        offer = client.post("/code-assets/license-offers", headers=headers, json={
            "business_id": "digital-products", "asset_id": asset.json()["id"],
            "buyer": "Digital buyer", "terms": "Draft offer only.",
        })
        assert offer.status_code == 201
        assert offer.json()["business_id"] == "digital-products"
        agency_offers = client.get("/code-assets/license-offers?business_id=physical-agency", headers=headers)
        assert all(item["id"] != offer.json()["id"] for item in agency_offers.json())



def test_approval_decisions_and_expense_mirroring_are_business_scoped(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(app) as client:
        agency_expense = client.post("/business/expenses", headers=headers, json={
            "business_id": "physical-agency",
            "title": "Agency logistics invoice",
            "amount": 30,
            "currency": "USD",
        })
        assert agency_expense.status_code == 201
        approval_id = agency_expense.json()["approval_id"]

        wrong_unit_decision = client.post(
            f"/approvals/{approval_id}/decision?business_id=digital-products",
            headers=headers, json={"decision": "approved"},
        )
        assert wrong_unit_decision.status_code == 404

        digital_expenses = client.get(
            "/business/expenses?business_id=digital-products", headers=headers
        )
        assert all(item["id"] != agency_expense.json()["id"] for item in digital_expenses.json())

        correct_decision = client.post(
            f"/approvals/{approval_id}/decision?business_id=physical-agency",
            headers=headers, json={"decision": "approved"},
        )
        assert correct_decision.status_code == 200
        assert correct_decision.json()["business_id"] == "physical-agency"

        agency_expenses = client.get(
            "/business/expenses?business_id=physical-agency", headers=headers
        )
        linked = next(item for item in agency_expenses.json() if item["id"] == agency_expense.json()["id"])
        assert linked["status"] == "approved_for_manual_payment"
