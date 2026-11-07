import pytest
from fastapi.testclient import TestClient
from ai_os.api import app
from ai_os.model_adapter import get_model_status, _endpoint
from ai_os.identity import issue_agent_token


def test_model_status_is_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    monkeypatch.delenv("AI_OS_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("AI_OS_MODEL_NAME", raising=False)
    status = get_model_status()
    assert status["enabled"] is False
    assert status["configured"] is False
    assert status["makes_network_request"] is False


def test_remote_model_endpoint_requires_https():
    with pytest.raises(ValueError):
        _endpoint("http://provider.example/v1")


def test_local_model_endpoint_allows_http():
    assert _endpoint("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"


def test_ceo_review_requires_specialist_report_before_model_call(monkeypatch):
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "false")
    with TestClient(app) as client:
        created = client.post("/company-runs", json={
            "title": "CEO model review test",
            "steps": [{"step_key": "research", "agent_id": "product-trend-researcher", "task": "Research demand"}]
        })
        assert created.status_code == 201
        response = client.post(f"/ceo/review/{created.json()['id']}")
    assert response.status_code == 422
    assert "No specialist reports" in response.json()["detail"]


def test_ceo_review_stores_structured_recommendations_without_executing_actions(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    def fake_generate(system_prompt, user_prompt):
        assert "untrusted data" in system_prompt
        assert "Research demand" in user_prompt
        return ({
            "summary": "Review complete",
            "decisions": ["Gather more buyer evidence"],
            "next_steps": [{"step": "Compare alternatives", "owner_agent_id": "product-trend-researcher", "rationale": "Evidence gap"}],
            "risks": ["Small sample"],
            "needs_owner_approval": True,
            "approval_reasons": ["Publishing requires approval"],
            "evidence_notes": ["One report received"]
        }, {"provider": "test", "model": "mock"})
    monkeypatch.setattr("ai_os.ceo_review.generate_json", fake_generate)
    with TestClient(app) as client:
        created = client.post("/company-runs", json={
            "title": "CEO model review test",
            "steps": [{"step_key": "research", "agent_id": "product-trend-researcher", "task": "Research demand"}]
        })
        run_id = created.json()["id"]
        dispatched = client.post(f"/company-runs/{run_id}/steps/research/dispatch")
        assert dispatched.status_code == 200
        token = issue_agent_token(
            "product-trend-researcher",
            run_id=run_id,
            capabilities=["step.report"],
        )
        reported = client.post(f"/company-runs/{run_id}/steps/research/report", json={
            "status": "completed", "summary": "Found evidence", "evidence": ["https://example.org/report"]
        }, headers={"X-AI-Agent-Token": token})
        assert reported.status_code == 200
        review = client.post(f"/ceo/review/{run_id}")
    assert review.status_code == 200, review.text
    result = review.json()
    assert result["accountable_agent_id"] == "company-orchestrator"
    assert result["needs_owner_approval"] is True
    assert result["actions_executed"] == []
    assert result["next_steps"][0]["execution_status"] == "recommendation_only"
    assert result["provider"] == "test"
