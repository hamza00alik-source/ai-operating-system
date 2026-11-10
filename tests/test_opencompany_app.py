import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from opencompany_app.api import app, get_store
from opencompany_core.persistence import SQLiteStore


client = TestClient(app)


@pytest.fixture
def owner_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    store = SQLiteStore(tmp_path / "owner-api.sqlite3")
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    store.close()


def test_health_reports_owner_authenticated_mode():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "owner-authenticated"


def test_workforce_endpoint_exposes_only_original_opencompany_roles():
    response = client.get("/workforce/roles")
    assert response.status_code == 200
    payload = response.json()
    assert payload["catalogue"] == "opencompany-original"
    assert payload["count"] == 10
    assert all(role["prohibited_actions"] for role in payload["roles"])



def test_original_department_endpoint_exposes_ten_department_contracts():
    response = client.get("/organization/departments")
    assert response.status_code == 200
    payload = response.json()
    assert payload["catalogue"] == "opencompany-original"
    assert payload["count"] == 10
    assert all(item["manager_role_key"] in item["role_keys"] for item in payload["departments"])
    assert all(item["approval_boundaries"] for item in payload["departments"])


def test_provider_status_never_exposes_secrets_and_defaults_disabled(monkeypatch):
    for name in (
        "OPENCOMPANY_OPENROUTER_API_KEY",
        "OPENCOMPANY_OPENROUTER_FREE_MODEL",
        "OPENCOMPANY_CONFIRM_OPENROUTER_FREE",
    ):
        monkeypatch.delenv(name, raising=False)
    response = client.get("/providers/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["gateway_enabled"] is False
    assert payload["billing_mode"] == "disabled"
    assert payload["paid_fallback"] is False
    assert payload["real_inference_verified"] is False


def test_provider_status_requires_explicit_free_confirmation(monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OPENROUTER_API_KEY", "do-not-return-this")
    monkeypatch.setenv("OPENCOMPANY_OPENROUTER_FREE_MODEL", "vendor/model:free")
    monkeypatch.delenv("OPENCOMPANY_CONFIRM_OPENROUTER_FREE", raising=False)
    response = client.get("/providers/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["gateway_enabled"] is False
    assert payload["partial_configuration_detected"] is True
    assert "do-not-return-this" not in response.text



def test_video_and_provider_endpoints_are_explicitly_not_active():
    video = client.get("/media/capabilities")
    assert video.status_code == 200
    capability = video.json()["capabilities"][0]
    assert capability["key"] == "longcat-video"
    assert capability["state"] == "researched_not_connected"

    providers = client.get("/providers/candidates")
    assert providers.status_code == 200
    assert providers.json()["gateway_enabled"] is False
    assert all(item["configured"] is False for item in providers.json()["candidates"])


def test_plan_preview_rejects_unknown_department():
    response = client.post("/plans/preview", json={"items": [{
        "id": str(uuid4()), "title": "Write report",
        "objective": "Prepare a sourced report", "department": "agency-agent-department",
    }]})
    assert response.status_code == 422


def test_plan_preview_identifies_ready_and_blocked_items_without_execution():
    prerequisite = uuid4()
    dependent = uuid4()
    response = client.post("/plans/preview", json={"items": [
        {"id": str(prerequisite), "title": "Collect evidence",
         "objective": "Gather public source evidence", "department": "intelligence-research",
         "state": "in_progress"},
        {"id": str(dependent), "title": "Write report",
         "objective": "Prepare a sourced report", "department": "intelligence-research",
         "state": "ready", "depends_on": [str(prerequisite)]},
    ]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready_item_ids"] == []
    assert payload["blocked_items"][0]["id"] == str(dependent)
    assert payload["execution_performed"] is False


def test_plan_preview_rejects_unknown_dependencies():
    response = client.post("/plans/preview", json={"items": [{
        "id": str(uuid4()), "title": "Write report",
        "objective": "Prepare a sourced report", "department": "intelligence-research",
        "depends_on": [str(uuid4())],
    }]})
    assert response.status_code == 422


def test_plan_preview_rejects_dependency_cycles():
    first, second = uuid4(), uuid4()
    response = client.post("/plans/preview", json={"items": [
        {"id": str(first), "title": "First", "objective": "First objective",
         "department": "customer-operations", "depends_on": [str(second)]},
        {"id": str(second), "title": "Second", "objective": "Second objective",
         "department": "customer-operations", "depends_on": [str(first)]},
    ]})
    assert response.status_code == 422


def test_company_records_require_owner_authentication(monkeypatch):
    monkeypatch.delenv("OPENCOMPANY_OWNER_API_KEY", raising=False)
    response = client.get("/work-items")
    assert response.status_code == 503


def test_wrong_owner_key_is_rejected(owner_client):
    response = owner_client.get("/work-items", headers={"X-OpenCompany-API-Key": "wrong"})
    assert response.status_code == 401


def test_owner_can_create_and_advance_work_item_with_audit(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Prepare market brief",
        "objective": "Create a sourced market brief for owner review",
        "department": "intelligence-research",
    })
    assert created.status_code == 200
    item_id = created.json()["item_id"]
    assert created.json()["state"] == "draft"

    for state in ("ready", "queued", "in_progress", "review", "completed"):
        response = owner_client.post(
            f"/work-items/{item_id}/transition", headers=headers,
            json={"target_state": state},
        )
        assert response.status_code == 200
        assert response.json()["state"] == state

    listed = owner_client.get("/work-items", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["state"] == "completed"

    audit = owner_client.get("/audit/verify", headers=headers)
    assert audit.status_code == 200
    assert audit.json() == {"event_count": 6, "chain_valid": True}


def test_owner_cannot_queue_dependent_work_before_prerequisite_completes(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    first = owner_client.post("/work-items", headers=headers, json={
        "title": "Gather source data", "objective": "Collect primary sources",
        "department": "intelligence-research",
    }).json()
    second = owner_client.post("/work-items", headers=headers, json={
        "title": "Write evidence brief", "objective": "Synthesize collected sources",
        "department": "intelligence-research", "depends_on": [first["item_id"]],
    }).json()
    ready = owner_client.post(
        f"/work-items/{second['item_id']}/transition", headers=headers,
        json={"target_state": "ready"},
    )
    assert ready.status_code == 200
    queued = owner_client.post(
        f"/work-items/{second['item_id']}/transition", headers=headers,
        json={"target_state": "queued"},
    )
    assert queued.status_code == 409
