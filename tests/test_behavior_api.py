import json

from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import connect
from ai_os.improvement_testing import run_proposal_regression_tests


def _seed_proposal():
    with connect() as db:
        db.execute(
            """INSERT INTO improvement_proposals
               (id,agent_id,title,problem,evidence_json,proposed_change,expected_impact,status,created_at)
               VALUES ('behavior-api-p1','product-trend-researcher','Evidence discipline',
                       'Missing source detail',?,
                       'Require source dates and include the supplied source URL in evidence.',
                       'Improve source grounding','approved_for_testing','2026-11-06T00:00:00Z')""",
            (json.dumps([{"evaluation_id":"e1"},{"evaluation_id":"e2"}]),),
        )


def _configure_local_model(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'behavior-api.sqlite3'}")
    token = "owner-behavior-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_BEHAVIOR_TEST_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "openai_compatible")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "local-test-model")
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)
    return {"Authorization": "Bearer " + token}


def test_owner_local_behavior_test_api_and_activation_gate(tmp_path, monkeypatch):
    headers = _configure_local_model(monkeypatch, tmp_path)
    from ai_os import behavior_testing
    def fake_generate(system, prompt):
        return ({
            "status":"completed",
            "summary":"The example changelog added CSV report export.",
            "evidence":["https://example.test/official-product-changelog (2026-10-29)"],
            "blockers":[],
        }, {"backend":"openai_compatible","model":"local-test-model"})
    monkeypatch.setattr(behavior_testing, "generate_json", fake_generate)
    with TestClient(app) as client:
        _seed_proposal()
        assert client.get("/behavior-tests/status", headers=headers).json()["enabled"] is True
        run_proposal_regression_tests("behavior-api-p1")
        denied = client.post("/improvement-proposals/behavior-api-p1/behavior-test")
        assert denied.status_code == 401
        tested = client.post(
            "/improvement-proposals/behavior-api-p1/behavior-test?fixture_id=source-grounded-research",
            headers=headers,
        )
        assert tested.status_code == 201
        assert tested.json()["passed"] is True
        history = client.get(
            "/improvement-proposals/behavior-api-p1/behavior-tests", headers=headers
        )
        assert len(history.json()) == 1
        activated = client.post("/improvement-proposals/behavior-api-p1/activate", headers=headers)
        assert activated.status_code == 201


def test_failed_behavior_test_blocks_activation(tmp_path, monkeypatch):
    headers = _configure_local_model(monkeypatch, tmp_path)
    from ai_os import behavior_testing
    responses = iter([
        {"status":"completed","summary":"Good source report","evidence":["https://example.test/official-product-changelog"],"blockers":[]},
        {"status":"completed","summary":"No evidence provided","evidence":[],"blockers":[]},
    ])
    monkeypatch.setattr(
        behavior_testing, "generate_json",
        lambda *args: (next(responses), {"backend":"openai_compatible","model":"local-test-model"}),
    )
    with TestClient(app) as client:
        _seed_proposal()
        run_proposal_regression_tests("behavior-api-p1")
        tested = client.post(
            "/improvement-proposals/behavior-api-p1/behavior-test",
            headers=headers,
        )
        assert tested.status_code == 201
        assert tested.json()["passed"] is False
        blocked = client.post("/improvement-proposals/behavior-api-p1/activate", headers=headers)
        assert blocked.status_code == 409
        assert "behavior test must pass" in blocked.json()["detail"]


def test_owner_dashboard_exposes_local_behavior_test_readiness_and_controls():
    with TestClient(app) as client:
        page = client.get("/dashboard")
    assert page.status_code == 200
    assert 'api("/behavior-tests/status")' in page.text
    assert "Run local model behavior test" in page.text
    assert "Activate tested version" in page.text
    assert "Rollback agent instructions" in page.text
    assert "testBehavior" in page.text
