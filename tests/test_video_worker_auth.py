from fastapi.testclient import TestClient

from ai_os.api import app


def test_video_worker_credentials_are_provider_scoped(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'provider-auth.db'}")
    monkeypatch.setenv("VIDEO_WORKER_TOKEN", "longcat-secret")
    monkeypatch.delenv("VIDEO_CINECODE_WORKER_TOKEN", raising=False)

    with TestClient(app) as client:
        # A LongCat secret must not make the Cinecode provider appear ready.
        status = client.get("/video/status?provider=cinecode", headers={"X-API-Key": "test-owner-key"})
        assert status.status_code == 200
        assert status.json()["worker_secret_configured"] is False
        monkeypatch.setenv("VIDEO_CINECODE_WORKER_TOKEN", "cinecode-secret")
        status = client.get("/video/status?provider=cinecode", headers={"X-API-Key": "test-owner-key"})
        assert status.json()["worker_secret_configured"] is True

        cinecode_headers = {
            "X-Video-Provider": "cinecode",
            "X-Video-Worker-Token": "cinecode-secret",
        }
        longcat_headers = {
            "X-Video-Provider": "longcat-video",
            "X-Video-Worker-Token": "longcat-secret",
        }

        # Each provider can authenticate only as itself.
        assert client.post(
            "/video/worker/claim",
            headers=cinecode_headers,
            json={"worker_id": "cine-worker", "provider": "cinecode"},
        ).status_code == 200
        assert client.post(
            "/video/worker/claim",
            headers=longcat_headers,
            json={"worker_id": "longcat-worker", "provider": "longcat-video"},
        ).status_code == 200

        # Changing the provider header cannot reuse the other provider's secret.
        assert client.post(
            "/video/worker/claim",
            headers={**longcat_headers, "X-Video-Provider": "cinecode"},
            json={"worker_id": "spoofed-worker", "provider": "cinecode"},
        ).status_code == 401
        assert client.post(
            "/video/worker/claim",
            headers={**cinecode_headers, "X-Video-Provider": "longcat-video"},
            json={"worker_id": "spoofed-worker", "provider": "longcat-video"},
        ).status_code == 401

        # The claim body must agree with the authenticated provider identity.
        assert client.post(
            "/video/worker/claim",
            headers=cinecode_headers,
            json={"worker_id": "mismatched-worker", "provider": "longcat-video"},
        ).status_code == 403
