from fastapi.testclient import TestClient

from ai_os.api import app


def test_owner_login_creates_persistent_cookie_session(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'sessions.db'}")

    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/auth/session", json={"api_key": "test-owner-key"})
        assert login.status_code == 200
        assert login.json()["authenticated"] is True
        assert "api_key" not in login.json()
        cookie = login.headers.get("set-cookie", "")
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=strict" in cookie

        # Session cookie replaces repeated X-API-Key headers for browser requests.
        assert client.get("/tasks").status_code == 200
        created = client.post(
            "/tasks",
            headers={"Origin": "https://testserver"},
            json={"title": "Session-authenticated task"},
        )
        assert created.status_code == 201

        logout = client.delete("/auth/session")
        assert logout.status_code == 200
        assert client.get("/tasks").status_code == 401


def test_company_department_registry_exposes_thirteen_departments():
    with TestClient(app) as client:
        response = client.get("/company/departments")
    assert response.status_code == 200
    payload = response.json()
    assert payload["department_count"] == 13
    assert payload["catalogued_agent_count"] == 283
    assert payload["runtime_model"].startswith("one shared worker")
    ids = {item["id"] for item in payload["departments"]}
    assert {"executive", "research", "design", "customer-support", "legal-compliance",
            "quality-assurance", "people-workforce", "social-media-video"} <= ids
    assert all(item["workflow_status"] == "catalogue-only" for item in payload["departments"] if item["id"] != "social-media-video")\n    social = next(item for item in payload["departments"] if item["id"] == "social-media-video")\n    assert social["workflow_status"] == "supervised-draft-workspace"


def test_workforce_manifest_has_full_agency_roster():
    with TestClient(app) as client:
        response = client.get("/workforce/agents")
    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_count"] == 283
    assert payload["department_count"] == 18
    assert payload["roles_including_ceo"] == 284
    assert len(payload["agents"]) == 283
