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


def test_company_department_registry_exposes_ten_opencompany_departments():
    with TestClient(app) as client:
        response = client.get("/company/departments")
    assert response.status_code == 200
    payload = response.json()
    assert payload["department_count"] == 10
    assert payload["catalogued_agent_count"] == 511
    assert payload["runtime_model"].startswith("OpenCompany-owned")
    ids = {item["id"] for item in payload["departments"]}
    assert {
        "intelligence-research", "product-innovation", "engineering",
        "design-creative", "marketing-growth", "sales-marketplace",
        "customer-operations", "finance-operations", "legal-compliance",
        "quality-workforce",
    } <= ids
    assert all(item["workflow_status"] == "catalogue-only" for item in payload["departments"])


def test_workforce_manifest_endpoint_serves_only_opencompany_roles():
    with TestClient(app) as client:
        response = client.get("/workforce/agents")
    assert response.status_code == 200
    payload = response.json()
    assert payload["catalogue"] == "opencompany-original"
    assert payload["agent_count"] == 511
    assert payload["department_count"] == 10
    assert payload["roles_including_ceo"] == 511
    assert payload["specialist_count"] == 500
    assert payload["leadership_role_count"] == 11
    assert len(payload["agents"]) == 511
    assert all(role["prohibited_actions"] for role in payload["agents"])
    assert all(role["playbook"]["workflow_steps"] for role in payload["agents"])
