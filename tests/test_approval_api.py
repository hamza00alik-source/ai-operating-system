from types import SimpleNamespace

from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import connect
from ai_os.identity import issue_agent_token


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'approval-api.sqlite3'}")
    monkeypatch.setenv("AI_OS_API_TOKEN", "owner-api-token-" + "x" * 40)
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "agent-signing-key-" + "y" * 40)
    from ai_os import registry
    monkeypatch.setattr(
        registry, "get_agent",
        lambda agent_id: SimpleNamespace(id=agent_id, enabled=True),
    )
    with TestClient(app):
        with connect() as db:
            db.execute(
                """INSERT INTO company_runs(id,title,description,status,created_at,updated_at)
                   VALUES ('api-run-1','Approval API run','Test run','running',
                           '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"""
            )
    return {"Authorization": "Bearer " + "owner-api-token-" + "x" * 40}


def _ceo_token():
    return issue_agent_token(
        "company-orchestrator", run_id="api-run-1", capabilities=["approval.request"]
    )


def _body():
    return {
        "action_type": "publish_product",
        "parameters": {
            "store": "primary-woocommerce",
            "product_id": "draft-123",
            "title": "Sample downloadable product",
            "price": "9.00",
            "currency": "USD",
        },
    }


def test_signed_ceo_request_owner_inbox_and_explicit_decision(tmp_path, monkeypatch):
    owner = _setup(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/ceo/approval-requests",
            json=_body(),
            headers={"X-AI-Agent-Token": _ceo_token()},
        )
        assert created.status_code == 201
        item = created.json()
        assert item["requested_by"] == "company-orchestrator"
        assert item["run_id"] == "api-run-1"
        assert item["status"] == "pending"
        assert item["parameters"]["product_id"] == "draft-123"

        assert client.get("/owner/approval-requests").status_code == 401
        inbox = client.get("/owner/approval-requests?status=pending", headers=owner)
        assert inbox.status_code == 200
        assert inbox.json()[0]["action_hash"] == item["action_hash"]

        denied = client.post(
            f"/owner/approval-requests/{item['id']}/decision",
            json={"decision": "approved", "action_hash": "0" * 64},
        )
        assert denied.status_code == 401

        approved = client.post(
            f"/owner/approval-requests/{item['id']}/decision",
            json={"decision": "approved", "action_hash": item["action_hash"]},
            headers=owner,
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        again = client.post(
            f"/owner/approval-requests/{item['id']}/decision",
            json={"decision": "approved", "action_hash": item["action_hash"]},
            headers=owner,
        )
        assert again.status_code == 409


def test_ceo_ingress_rejects_missing_or_specialist_identity(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    specialist = issue_agent_token(
        "marketing-content-creator", run_id="api-run-1", capabilities=["step.report"]
    )
    with TestClient(app) as client:
        assert client.post("/ceo/approval-requests", json=_body()).status_code == 401
        denied = client.post(
            "/ceo/approval-requests", json=_body(),
            headers={"X-AI-Agent-Token": specialist},
        )
        assert denied.status_code == 403
        # Only the exact CEO POST ingress bypasses the owner-token middleware.
        assert client.get("/ceo/approval-requests").status_code == 401


def test_ceo_ingress_rejects_unknown_actions_and_extra_fields(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    with TestClient(app) as client:
        invalid_action = client.post(
            "/ceo/approval-requests",
            json={"action_type": "run_shell", "parameters": {"command": "echo unsafe"}},
            headers={"X-AI-Agent-Token": _ceo_token()},
        )
        assert invalid_action.status_code == 403
        invalid_payload = client.post(
            "/ceo/approval-requests",
            json={**_body(), "requested_by": "company-orchestrator"},
            headers={"X-AI-Agent-Token": _ceo_token()},
        )
        assert invalid_payload.status_code == 422


def test_ceo_ingress_does_not_consume_token_for_missing_run(tmp_path, monkeypatch):
    owner = _setup(monkeypatch, tmp_path)
    token = issue_agent_token(
        "company-orchestrator", run_id="not-a-real-run", capabilities=["approval.request"]
    )
    with TestClient(app) as client:
        missing = client.post(
            "/ceo/approval-requests", json=_body(),
            headers={"X-AI-Agent-Token": token},
        )
        assert missing.status_code == 409
        with connect() as db:
            db.execute(
                """INSERT INTO company_runs(id,title,description,status,created_at,updated_at)
                   VALUES ('not-a-real-run','Now exists','Test','running',
                           '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"""
            )
        retried = client.post(
            "/ceo/approval-requests", json=_body(),
            headers={"X-AI-Agent-Token": token},
        )
        assert retried.status_code == 201
        assert client.get("/owner/approval-requests", headers=owner).status_code == 200
