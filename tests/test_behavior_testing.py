import json

import pytest

from ai_os.db import connect, initialize_database
from ai_os.improvement_testing import run_proposal_regression_tests
from ai_os.behavior_testing import (
    get_behavior_test_status,
    list_behavior_test_runs,
    run_behavior_regression_test,
)


def _seed(path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{path}")
    initialize_database()
    with connect() as db:
        db.execute(
            """INSERT INTO improvement_proposals
               (id,agent_id,title,problem,evidence_json,proposed_change,expected_impact,status,created_at)
               VALUES ('behavior-p1','product-trend-researcher','Evidence discipline',
                       'Missing source detail',?,
                       'Require source dates and include the supplied source URL in evidence.',
                       'Improve source grounding','approved_for_testing','2026-11-06T00:00:00Z')""",
            (json.dumps([{"evaluation_id":"e1"},{"evaluation_id":"e2"}]),),
        )


def test_behavior_testing_is_disabled_without_explicit_local_opt_in(monkeypatch):
    monkeypatch.delenv("AI_OS_BEHAVIOR_TEST_ENABLED", raising=False)
    monkeypatch.delenv("AI_OS_MODEL_ENABLED", raising=False)
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)
    status = get_behavior_test_status()
    assert status["enabled"] is False
    assert status["reason"] == "behavior_test_opt_in_disabled"


@pytest.mark.parametrize("base_url,backend,api_key,reason", [
    ("https://remote.example/v1", "openai_compatible", "", "remote_model_endpoints"),
    ("http://localhost:8000/v1", "command", "", "only_openai_compatible"),
    ("http://localhost:8000/v1", "openai_compatible", "secret", "API_key_must_be_unset"),
])
def test_behavior_testing_rejects_remote_cli_or_key(monkeypatch, base_url, backend, api_key, reason):
    monkeypatch.setenv("AI_OS_BEHAVIOR_TEST_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", backend)
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", base_url)
    monkeypatch.setenv("AI_OS_MODEL_NAME", "local-test-model")
    monkeypatch.setenv("AI_OS_MODEL_API_KEY", api_key)
    status = get_behavior_test_status()
    assert status["enabled"] is False
    assert reason in status["reason"]


def test_local_behavior_comparison_is_persisted_and_never_activates(tmp_path, monkeypatch):
    _seed(tmp_path / "behavior.sqlite3", monkeypatch)
    run_proposal_regression_tests("behavior-p1")
    monkeypatch.setenv("AI_OS_BEHAVIOR_TEST_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "openai_compatible")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "local-test-model")
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)
    from ai_os import behavior_testing
    calls = []
    def fake_generate(system, prompt):
        calls.append(prompt)
        return ({
            "status": "completed",
            "summary": "The example changelog added CSV report export.",
            "evidence": ["https://example.test/official-product-changelog (2026-10-29)"],
            "blockers": [],
        }, {"backend": "openai_compatible", "model": "local-test-model"})
    monkeypatch.setattr(behavior_testing, "generate_json", fake_generate)
    result = run_behavior_regression_test("behavior-p1", "source-grounded-research")
    assert result["passed"] is True
    assert result["score_delta"] == 0
    assert result["details"]["signal"] == "no_regression_only"
    assert len(calls) == 2
    assert "CANDIDATE INSTRUCTION ADDENDUM" in calls[1]
    assert "COMPANY GOVERNANCE — HIGHEST PRIORITY" in calls[1]
    from ai_os.instruction_versions import get_active_instruction
    assert get_active_instruction("product-trend-researcher")["active_version_id"] == result["active_version_id"]
    history = list_behavior_test_runs("behavior-p1")
    assert len(history) == 1
    assert history[0]["passed"] is True


def test_candidate_behavior_regression_fails_when_candidate_score_drops(tmp_path, monkeypatch):
    _seed(tmp_path / "behavior-fail.sqlite3", monkeypatch)
    run_proposal_regression_tests("behavior-p1")
    monkeypatch.setenv("AI_OS_BEHAVIOR_TEST_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "openai_compatible")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "local-test-model")
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)
    from ai_os import behavior_testing
    responses = iter([
        {"status":"completed","summary":"Good report","evidence":["https://example.test/official-product-changelog"],"blockers":[]},
        {"status":"completed","summary":"Cannot verify","evidence":[],"blockers":[]},
    ])
    monkeypatch.setattr(behavior_testing, "generate_json", lambda *args: (next(responses), {"backend":"openai_compatible","model":"local-test-model"}))
    result = run_behavior_regression_test("behavior-p1", "source-grounded-research")
    assert result["passed"] is False
    assert result["score_delta"] < 0


def test_behavior_result_is_stale_after_another_proposal_changes_active_baseline(tmp_path, monkeypatch):
    _seed(tmp_path / "behavior-stale.sqlite3", monkeypatch)
    with connect() as db:
        db.execute(
            """INSERT INTO improvement_proposals
               (id,agent_id,title,problem,evidence_json,proposed_change,expected_impact,status,created_at)
               VALUES ('behavior-p2','product-trend-researcher','Second change','Another issue',?,
                       'Require concise summaries and list missing source evidence.',
                       'Improve summaries','approved_for_testing','2026-11-06T00:00:01Z')""",
            (json.dumps([{"evaluation_id":"e3"},{"evaluation_id":"e4"}]),),
        )
    run_proposal_regression_tests("behavior-p1")
    run_proposal_regression_tests("behavior-p2")
    monkeypatch.setenv("AI_OS_BEHAVIOR_TEST_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "openai_compatible")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "local-test-model")
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)
    from ai_os import behavior_testing
    from ai_os.instruction_versions import activate_tested_proposal
    monkeypatch.setattr(
        behavior_testing, "generate_json",
        lambda *args: ({
            "status":"completed","summary":"Source fact","evidence":["https://example.test/official-product-changelog (2026-10-29)"],
            "blockers":[],
        }, {"backend":"openai_compatible","model":"local-test-model"}),
    )
    run_behavior_regression_test("behavior-p1", "source-grounded-research")
    activate_tested_proposal("behavior-p2", actor="owner:test")
    with pytest.raises(ValueError, match="baseline changed"):
        activate_tested_proposal("behavior-p1", actor="owner:test")
