import pytest
from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import initialize_database


@pytest.fixture
def session_client(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "owner-session-test-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "owner-session.db"))
    monkeypatch.delenv("AI_OS_TRUSTED_ORIGINS", raising=False)
    initialize_database()
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/auth/session", json={"api_key": "owner-session-test-key"})
        assert login.status_code == 200
        yield client


def test_owner_session_allows_write_from_trusted_vercel_origin(session_client):
    response = session_client.post(
        "/brain/memories/not-a-real-memory/review",
        headers={
            "Origin": "https://ai-operating-system-one.vercel.app",
            "X-Forwarded-Proto": "https",
        },
        json={"decision": "rejected", "note": "auth regression test"},
    )
    # 404 proves the owner session passed authentication and reached the handler.
    assert response.status_code == 404


def test_owner_session_rejects_untrusted_cross_site_origin(session_client):
    response = session_client.post(
        "/brain/memories/not-a-real-memory/review",
        headers={
            "Origin": "https://attacker.example",
            "X-Forwarded-Proto": "https",
        },
        json={"decision": "rejected", "note": "auth regression test"},
    )
    assert response.status_code == 401
