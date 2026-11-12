from fastapi.testclient import TestClient

from ai_os.api import app


def test_social_content_requires_owner_approval_before_any_external_action(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'social.db'}")
    headers = {"X-API-Key": "test-owner-key"}

    with TestClient(app) as client:
        status = client.get("/social/status", headers=headers)
        assert status.status_code == 200
        assert status.json()["publishing_enabled"] is False

        created = client.post(
            "/social/content?kind=social_post",
            headers=headers,
            json={
                "title": "Launch post",
                "body": "Draft copy only",
                "channels": ["instagram", "youtube"],
                "content_type": "post",
            },
        )
        assert created.status_code == 201
        item = created.json()
        assert item["status"] == "draft"

        requested = client.post(
            f"/social/content/{item['id']}/request-approval", headers=headers
        )
        assert requested.status_code == 200
        assert requested.json()["content"]["status"] == "awaiting_approval"

        decided = client.post(
            f"/social/content/{item['id']}/decision",
            headers=headers,
            json={"decision": "approved"},
        )
        assert decided.status_code == 200
        assert decided.json()["content"]["status"] == "approved_for_scheduling"
        assert decided.json()["publishing_performed"] is False


def test_social_content_rejects_unknown_channels(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'social-invalid.db'}")
    with TestClient(app) as client:
        response = client.post(
            "/social/content?kind=social_post",
            headers={"X-API-Key": "test-owner-key"},
            json={"title": "Invalid", "channels": ["made-up-network"]},
        )
    assert response.status_code == 422
