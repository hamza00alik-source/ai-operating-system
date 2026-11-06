import json

from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import connect


def _seed_proposal():
    with connect() as db:
        db.execute(
            """INSERT INTO improvement_proposals
               (id,agent_id,title,problem,evidence_json,proposed_change,expected_impact,status,created_at)
               VALUES ('api-instruction-proposal','product-trend-researcher','Evidence quality',
                       'Repeated report failures',?,
                       'Require source dates and distinguish observed facts from assumptions.',
                       'Improve clarity','approved_for_testing','2026-11-06T00:00:00Z')""",
            (json.dumps([{"evaluation_id":"ev-1"},{"evaluation_id":"ev-2"}]),),
        )


def test_owner_token_required_for_activation_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'instruction-api.sqlite3'}")
    token = "owner-instruction-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    monkeypatch.setenv("AI_OS_ENV", "production")
    with TestClient(app) as client:
        _seed_proposal()
        denied = client.post("/improvement-proposals/api-instruction-proposal/activate")
        assert denied.status_code == 401
        headers = {"Authorization": "Bearer " + token}
        before = client.get("/agents/product-trend-researcher/instructions", headers=headers)
        assert before.status_code == 200
        assert before.json()["version_number"] == 1
        blocked = client.post("/improvement-proposals/api-instruction-proposal/activate", headers=headers)
        assert blocked.status_code == 409
        tested = client.post("/improvement-proposals/api-instruction-proposal/test", headers=headers)
        assert tested.status_code == 201
        assert tested.json()["passed"] is True
        activated = client.post("/improvement-proposals/api-instruction-proposal/activate", headers=headers)
        assert activated.status_code == 201
        assert activated.json()["version_number"] == 2
        current = client.get("/agents/product-trend-researcher/instructions", headers=headers)
        assert current.json()["content"] == activated.json()["content"]
        history = client.get("/agents/product-trend-researcher/instructions/history", headers=headers)
        assert history.status_code == 200
        assert len(history.json()) == 2
        rolled_back = client.post("/agents/product-trend-researcher/instructions/rollback", headers=headers)
        assert rolled_back.status_code == 200
        assert rolled_back.json()["version_number"] == 1
        assert client.get("/audit/verify", headers=headers).json()["valid"] is True


def test_instruction_activation_does_not_happen_automatically_after_test(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'instruction-no-auto.sqlite3'}")
    monkeypatch.delenv("AI_OS_API_TOKEN", raising=False)
    monkeypatch.setenv("AI_OS_ENV", "development")
    with TestClient(app) as client:
        _seed_proposal()
        before = client.get("/agents/product-trend-researcher/instructions").json()
        tested = client.post("/improvement-proposals/api-instruction-proposal/test")
        assert tested.status_code == 201
        after = client.get("/agents/product-trend-researcher/instructions").json()
        assert after["active_version_id"] == before["active_version_id"]
        assert after["version_number"] == 1
        denied_activation = client.post("/improvement-proposals/api-instruction-proposal/activate")
        denied_rollback = client.post("/agents/product-trend-researcher/instructions/rollback")
        assert denied_activation.status_code == 403
        assert denied_rollback.status_code == 403


def test_unknown_agent_instruction_endpoints_return_404(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'instruction-unknown.sqlite3'}")
    monkeypatch.delenv("AI_OS_API_TOKEN", raising=False)
    monkeypatch.setenv("AI_OS_ENV", "development")
    with TestClient(app) as client:
        assert client.get("/agents/not-a-real-agent/instructions").status_code == 404
        assert client.post("/agents/not-a-real-agent/instructions/rollback").status_code == 404
