from fastapi.testclient import TestClient

from ai_os.api import app


def test_production_accepts_deployment_api_key_alias_and_x_api_key_header(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.delenv("AI_OS_API_TOKEN", raising=False)
    monkeypatch.setenv("AI_OS_API_KEY", "deployment-owner-key-" + "x" * 32)
    with TestClient(app) as client:
        denied = client.get("/runtime")
        accepted = client.get(
            "/runtime",
            headers={"X-API-Key": "deployment-owner-key-" + "x" * 32},
        )
    assert denied.status_code == 401
    assert accepted.status_code == 200


def test_owner_token_takes_precedence_over_api_key_alias(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_TOKEN", "canonical-owner-token-" + "x" * 32)
    monkeypatch.setenv("AI_OS_API_KEY", "deployment-owner-key-" + "x" * 32)
    with TestClient(app) as client:
        alias_only = client.get(
            "/runtime",
            headers={"X-API-Key": "deployment-owner-key-" + "x" * 32},
        )
        canonical = client.get(
            "/runtime",
            headers={"Authorization": "Bearer canonical-owner-token-" + "x" * 32},
        )
    assert alias_only.status_code == 401
    assert canonical.status_code == 200
