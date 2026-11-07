from fastapi.testclient import TestClient
from ai_os.api import app


def test_department_directory_exposes_full_company_org():
    with TestClient(app) as client:
        response = client.get("/company/departments")
    assert response.status_code == 200
    payload = response.json()
    assert payload["accountable_agent_id"] == "company-orchestrator"
    departments = payload["departments"]
    assert len(departments) >= 12
    ids = {item["id"] for item in departments}
    assert {"research", "product", "engineering", "marketing", "sales",
            "ecommerce", "support", "finance", "operations", "quality",
            "people", "analytics"} <= ids
    assert all("mission" in item and item["workstreams"] for item in departments)
    assert all(item["execution_enabled"] is False for item in departments)


def test_department_detail_is_read_only_and_unknown_department_is_404():
    with TestClient(app) as client:
        known = client.get("/company/departments/research")
        unknown = client.get("/company/departments/not-a-department")
    assert known.status_code == 200
    assert known.json()["id"] == "research"
    assert unknown.status_code == 404
