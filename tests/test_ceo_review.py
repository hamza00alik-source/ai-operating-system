from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.execution import create_company_run, dispatch_ready_step, submit_step_report
from ai_os.execution_schemas import CompanyRunCreate, RunStepCreate, StepReportCreate


def _setup(monkeypatch, tmp_path):
    owner_token = "ceo-review-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'ceo-review.sqlite3'}")
    monkeypatch.setenv("AI_OS_API_TOKEN", owner_token)
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "ceo-review-signing-key-" + "y" * 40)
    with TestClient(app):
        run = create_company_run(CompanyRunCreate(
            title="Prepare a digital product draft",
            description="Research and prepare a potential downloadable product.",
            steps=[RunStepCreate(
                step_key="research",
                agent_id="product-trend-researcher",
                task="Assess demand and recommend a suitable digital product.",
                context="Use supplied evidence only.",
            )],
        ))
        dispatch_ready_step(run["id"], "research")
        submit_step_report(
            run["id"],
            "research",
            StepReportCreate(
                status="completed",
                summary="The research supports preparing an unpublished product draft.",
                evidence=["The specialist report identified a concrete draft opportunity."],
                blockers=[],
            ),
        )
    return run["id"], {"Authorization": "Bearer " + owner_token}


def test_ceo_review_creates_signed_owner_request_for_supported_draft_only(
    monkeypatch, tmp_path
):
    run_id, owner = _setup(monkeypatch, tmp_path)
    calls = []

    def fake_generate(system_prompt, user_prompt):
        calls.append((system_prompt, user_prompt))
        return ({
            "summary": "The specialist evidence supports preparing a product draft.",
            "decisions": ["Prepare an unpublished draft for owner inspection."],
            "next_steps": [],
            "risks": ["The product must not be published without a separate approval."],
            "needs_owner_approval": True,
            "approval_reasons": ["Owner must inspect the exact draft and price."],
            "evidence_notes": ["The specialist report supports the draft concept."],
            "proposed_owner_actions": [
                {
                    "action_type": "create_product_draft",
                    "parameters": {
                        "name": "Original digital guide",
                        "description": "A downloadable guide draft.",
                        "regular_price": "4.99",
                    },
                    "rationale": "Create an unpublished product draft for owner review.",
                },
                {
                    "action_type": "publish_product",
                    "parameters": {"product_id": "123"},
                    "rationale": "This action is not supported by a publishing adapter.",
                },
            ],
        }, {"provider": "test", "model": "mock-ceo"})

    monkeypatch.setattr("ai_os.ceo_review.generate_json", fake_generate)
    with TestClient(app) as client:
        response = client.post(f"/ceo/review/{run_id}", headers=owner)
        assert response.status_code == 200, response.text
        review = response.json()
        assert review["accountable_agent_id"] == "company-orchestrator"
        assert review["actions_executed"] == []
        assert len(review["owner_approval_requests"]) == 1
        assert len(review["rejected_owner_action_proposals"]) == 1
        request = review["owner_approval_requests"][0]
        assert request["action_type"] == "create_product_draft"
        assert request["status"] == "pending"
        assert request["parameters"]["regular_price"] == "4.99"
        assert "token" not in str(review).lower()

        inbox = client.get("/owner/approval-requests?status=pending", headers=owner)
        assert inbox.status_code == 200
        assert any(item["id"] == request["id"] for item in inbox.json())

        repeated_review = client.post(f"/ceo/review/{run_id}", headers=owner)
        assert repeated_review.status_code == 200, repeated_review.text
        repeated_request = repeated_review.json()["owner_approval_requests"][0]
        assert repeated_request["id"] == request["id"]
        assert repeated_request["reused_existing_request"] is True
        inbox_after_repeat = client.get("/owner/approval-requests?status=pending", headers=owner)
        assert len(inbox_after_repeat.json()) == 1

    assert "You are **AgentsOrchestrator**" in calls[0][0]
    assert "AI OPERATING SYSTEM GOVERNANCE" in calls[0][0]
    assert "You may propose an owner-approval request" in calls[0][0]
    assert "never execute" in calls[0][0].lower()


def test_ceo_review_rejects_secret_bearing_action_parameters(monkeypatch, tmp_path):
    run_id, owner = _setup(monkeypatch, tmp_path)

    def fake_generate(system_prompt, user_prompt):
        return ({
            "summary": "Review completed.",
            "proposed_owner_actions": [{
                "action_type": "create_product_draft",
                "parameters": {
                    "name": "Unsafe draft",
                    "description": "Draft text",
                    "regular_price": "1.00",
                    "api_token": "must-not-be-stored",
                },
                "rationale": "This proposal includes a forbidden secret field.",
            }],
        }, {"provider": "test", "model": "mock-ceo"})

    monkeypatch.setattr("ai_os.ceo_review.generate_json", fake_generate)
    with TestClient(app) as client:
        response = client.post(f"/ceo/review/{run_id}", headers=owner)
        assert response.status_code == 200, response.text
        review = response.json()
        assert review["owner_approval_requests"] == []
        assert len(review["rejected_owner_action_proposals"]) == 1
        inbox = client.get("/owner/approval-requests?status=pending", headers=owner)
        assert inbox.status_code == 200
        assert inbox.json() == []
