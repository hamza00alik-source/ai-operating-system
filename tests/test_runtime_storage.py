"""Deployment storage checks for the owner-authenticated runtime."""

from fastapi.testclient import TestClient

from opencompany_app.api import app, get_runtime
from opencompany_app.runtime import create_runtime


def test_owner_session_can_be_created_and_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    monkeypatch.setenv("OPENCOMPANY_COOKIE_SECURE", "true")
    runtime = create_runtime(str(tmp_path / "owner-session.sqlite3"))
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = client.post("/auth/session", json={"api_key": "test-owner-key"})
            assert response.status_code == 200
            assert response.json()["authenticated"] is True
            token = response.cookies.get("opencompany_session")
            assert token
            assert runtime.sessions.validate(token)
    finally:
        app.dependency_overrides.clear()
        runtime.close()


def test_readiness_rejects_read_only_database(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    runtime = create_runtime(str(tmp_path / "readonly.sqlite3"))
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app) as client:
            runtime.store._connection.execute("PRAGMA query_only = ON")
            response = client.get("/ready")
            assert response.status_code == 503
            assert response.json()["detail"] == "OpenCompany storage is not ready."
            runtime.store._connection.execute("PRAGMA query_only = OFF")
    finally:
        app.dependency_overrides.clear()
        runtime.close()
