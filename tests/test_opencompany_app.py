import pytest
import hashlib
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from uuid import UUID, uuid4

import opencompany_app.api as api_module
from opencompany_app.api import app, get_store, get_delegation_store, get_runtime
from opencompany_app.runtime import WorkItem, create_runtime
from opencompany_core.persistence import SQLiteStore
from opencompany_core.asset_storage import PrivateFilesystemAssetStorage
from opencompany_core.domain import AuditRecord, TaskState
from opencompany_core.execution import AgentDeliverable
from opencompany_core.delegation_records import DelegationRepository
from opencompany_core.model_gateway import BillingMode, ModelGateway, ModelResult, ProviderPolicy, ProviderUnavailable
from opencompany_core.github_evolution import GitHubPullRequest


client = TestClient(app)


@pytest.fixture
def owner_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    database = tmp_path / "owner-api.sqlite3"
    runtime = create_runtime(str(database))
    store = runtime.store
    delegations = runtime.delegations
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_delegation_store] = lambda: delegations
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
    runtime.close()


def test_owner_dashboard_is_served_without_embedded_secrets_and_with_security_headers():
    response = client.get("/owner")
    assert response.status_code == 200
    assert "OpenCompany · Owner Control Center" in response.text
    assert "Owner sign in" in response.text
    assert 'id="login-form"' in response.text
    assert 'id="owner-key"' in response.text
    assert 'id="dashboard"' in response.text
    assert 'id="refresh"' in response.text
    assert 'id="bootstrap-ceo"' in response.text
    assert 'id="bootstrap-managers"' in response.text
    assert 'id="bootstrap-specialists"' in response.text
    assert "Workspace" in response.text
    assert 'id="task-form"' in response.text
    assert 'id="task-business"' in response.text
    assert 'id="task-department"' in response.text
    assert 'id="worker-status"' in response.text
    assert 'id="usage"' in response.text
    assert 'id="finance"' in response.text
    assert 'id="departments"' in response.text
    assert 'id="task-detail"' in response.text
    assert 'id="memory-business"' in response.text
    assert 'id="memory-form"' in response.text
    assert 'id="memory-key"' in response.text
    assert 'id="memory-category"' in response.text
    assert 'id="memory-source"' in response.text
    assert 'id="memory-content"' in response.text
    assert 'id="memory-confirm"' in response.text
    assert 'id="memory-list"' in response.text
    assert 'id="integration-list"' in response.text
    assert 'id="credential-list"' in response.text
    assert "confirm_owner_write" in response.text
    assert "refreshBusinessContext" in response.text
    assert '"/business-units/"+encodeURIComponent(business)+"/memory"' in response.text
    assert '"/business-units/"+encodeURIComponent(business)+"/integrations"' in response.text
    assert '"/business-units/"+encodeURIComponent(business)+"/credentials"' in response.text
    assert "Agent writes remain disabled" in response.text
    assert 'id="ceo-cycle"' in response.text
    assert 'id="budget-form"' in response.text
    assert 'id="budget-rationale"' in response.text
    assert 'id="reconciliation-form"' in response.text
    assert 'id="reconciliation-list"' in response.text
    assert 'id="integration-form"' in response.text
    assert 'id="ops-business"' in response.text
    assert 'id="counterparty-form"' in response.text
    assert 'id="product-form"' in response.text
    assert 'id="order-form"' in response.text
    assert 'id="product-list"' in response.text
    assert 'id="order-list"' in response.text
    assert 'id="treasury-business"' in response.text
    assert 'id="treasury-account-form"' in response.text
    assert 'id="treasury-spend-form"' in response.text
    assert 'id="treasury-accounts"' in response.text
    assert 'id="treasury-requests"' in response.text
    assert "refreshTreasury" in response.text
    assert "No money was transferred" in response.text
    assert "refreshBusinessOperations" in response.text
    assert '"/finance/budgets"' in response.text
    assert '"/finance/reconciliations"' in response.text
    assert '"/finance/budgets/history"' in response.text
    assert '"/integrations/"+encodeURIComponent(item.integration_id)+"/review"' in response.text
    assert 'id="advance-work"' in response.text
    assert 'id="worker-start"' in response.text
    assert 'id="worker-stop"' in response.text
    assert "Create team proposal" in response.text
    assert "Show proposals" in response.text
    assert "Approve & create child tasks" in response.text
    assert "Reject proposal" in response.text
    assert "Admit to queue" in response.text
    assert "Run one task" in response.text
    assert "Approve deliverable" in response.text
    assert "Reject deliverable" in response.text
    assert '"/work-items/"+encodeURIComponent(item.id)+"/delegation-proposals"' in response.text
    assert '"/workers/run-once"' in response.text
    assert '"/executive/orchestration/advance"' in response.text
    assert 'api("/executive/orchestration/status")' in response.text
    assert 'api("/workers/service-status")' in response.text
    assert 'api("/usage/model")' in response.text
    assert 'api("/finance/entries")' in response.text
    assert "Create draft work item" in response.text
    assert "No execution was started" in response.text
    assert "No paid fallback" in response.text
    assert "No automatic customer contact, publishing or payments" in response.text
    assert "textContent" in response.text
    assert "sessionStorage" not in response.text
    assert "localStorage" not in response.text
    assert "OPENCOMPANY_OWNER_API_KEY" not in response.text
    assert "onclick=" not in response.text
    assert "@media(max-width:560px)" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "unsafe-inline" not in response.headers["content-security-policy"].split("script-src", 1)[1].split(";", 1)[0]
    assert "nonce-" in response.headers["content-security-policy"]
    assert 'nonce="' in response.text
    style_policy = response.headers["content-security-policy"].split("style-src", 1)[1].split(";", 1)[0]
    assert "unsafe-inline" not in style_policy
    assert "style-src-attr" not in response.headers["content-security-policy"]
    assert " style=" not in response.text
    assert "<style nonce=" in response.text
    assert response.headers["x-frame-options"] == "DENY"

def test_health_reports_owner_authenticated_mode():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "owner-authenticated"


def test_provider_status_exposes_unorouter_as_company_provider_without_secret(monkeypatch):
    monkeypatch.delenv("OPENCOMPANY_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENCOMPANY_OPENROUTER_FREE_MODEL", raising=False)
    monkeypatch.delenv("OPENCOMPANY_CONFIRM_OPENROUTER_FREE", raising=False)
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "never-return-this-secret")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "sample/chat-model:free")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "true")
    response = client.get("/providers/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["gateway_enabled"] is True
    assert payload["provider"] == "unorouter"
    assert payload["providers"]["unorouter"]["configured"] is True
    assert payload["providers"]["unorouter"]["model"] == "sample/chat-model:free"
    assert payload["paid_fallback"] is False
    assert "never-return-this-secret" not in response.text


def test_provider_status_keeps_unorouter_disabled_without_owner_confirmation(monkeypatch):
    monkeypatch.delenv("OPENCOMPANY_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENCOMPANY_OPENROUTER_FREE_MODEL", raising=False)
    monkeypatch.delenv("OPENCOMPANY_CONFIRM_OPENROUTER_FREE", raising=False)
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "sample/chat-model:free")
    monkeypatch.delenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", raising=False)
    response = client.get("/providers/status")
    assert response.status_code == 200
    assert response.json()["gateway_enabled"] is False
    assert response.json()["providers"]["unorouter"]["partial_configuration_detected"] is True


def test_unorouter_discovery_requires_owner_and_returns_only_free_models(owner_client, monkeypatch):
    discovered = [{
        "id": "provider/model:free", "name": "provider/model:free", "vendor": "Example",
        "context_length": 32768, "max_output_tokens": 4096,
    }]
    monkeypatch.setattr(api_module, "discover_free_models", lambda api_key: discovered if api_key == "valid-api-key-123456" else [])
    unauthorized = owner_client.post(
        "/settings/providers/unorouter/discover",
        json={"api_key": "valid-api-key-123456"},
    )
    assert unauthorized.status_code == 401

    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    response = owner_client.post(
        "/settings/providers/unorouter/discover",
        headers=headers,
        json={"api_key": "valid-api-key-123456"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["models"][0]["id"] == "provider/model:free"
    assert payload["paid_models_included"] is False
    assert "valid-api-key-123456" not in response.text


def test_unorouter_save_revalidates_model_before_persisting(owner_client, monkeypatch):
    monkeypatch.setattr(api_module, "discover_free_models", lambda api_key: [])
    response = owner_client.put(
        "/settings/providers/unorouter",
        headers={"X-OpenCompany-API-Key": "test-owner-key"},
        json={
            "api_key": "valid-api-key-123456",
            "model": "provider/model:free",
            "confirm_free": True,
        },
    )
    assert response.status_code == 409
    assert owner_client.get(
        "/settings/providers/unorouter",
        headers={"X-OpenCompany-API-Key": "test-owner-key"},
    ).json()["configured"] is False


def test_workforce_endpoint_exposes_only_original_opencompany_roles():
    response = client.get("/workforce/roles")
    assert response.status_code == 200
    payload = response.json()
    assert payload["catalogue"] == "opencompany-original"
    assert payload["count"] == 511
    assert payload["specialist_count"] == 500
    assert payload["leadership_role_count"] == 11
    assert payload["team_count"] == 100
    assert all(role["prohibited_actions"] for role in payload["roles"])
    assert all(role["team_key"] for role in payload["roles"])
    assert all(role["playbook"]["workflow_steps"] and role["playbook"]["quality_rubric"] for role in payload["roles"])



def test_department_route_preview_selects_only_that_department_specialists():
    response = client.post("/workforce/route-preview", json={
        "department": "intelligence-research",
        "required_capabilities": ["market", "researcher"],
        "limit": 5,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] > 0
    assert payload["candidates"][0]["title"] == "Market Demand Researcher"
    assert all(candidate["team_key"].startswith("intelligence-research__") for candidate in payload["candidates"])
    assert payload["assignment_performed"] is False
    assert payload["execution_started"] is False


def test_department_route_preview_rejects_unknown_department():
    response = client.post("/workforce/route-preview", json={
        "department": "not-a-department",
        "required_capabilities": ["research"],
    })
    assert response.status_code == 422


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


def test_owner_can_bootstrap_ten_draft_department_managers(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    first = owner_client.post("/agents/bootstrap", headers=headers)
    assert first.status_code == 200
    assert first.json()["count"] == 10
    assert first.json()["all_draft"] is True
    assert first.json()["execution_started"] is False

    second = owner_client.post("/agents/bootstrap", headers=headers)
    assert second.status_code == 200
    assert second.json()["count"] == 10

    listed = owner_client.get("/agents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 10
    assert all(item["state"] == "draft" for item in listed.json()["agents"])


def test_owner_can_activate_manager_profile_without_starting_worker(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    agent = owner_client.get("/agents", headers=headers).json()["agents"][0]
    assert agent["role_key"] and agent["team_key"]

    response = owner_client.post(
        f"/agents/{agent['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": agent["revision"]},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "active"
    assert response.json()["revision"] == agent["revision"] + 1
    assert response.json()["worker_started"] is False

    updated = owner_client.get("/agents", headers=headers).json()["agents"]
    assert next(item for item in updated if item["id"] == agent["id"])["state"] == "active"


def test_agent_activation_rejects_stale_revision(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    agent = owner_client.get("/agents", headers=headers).json()["agents"][0]
    changed = owner_client.post(
        f"/agents/{agent['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": agent["revision"]},
    )
    assert changed.status_code == 200
    stale = owner_client.post(
        f"/agents/{agent['id']}/state", headers=headers,
        json={"target_state": "paused", "expected_revision": agent["revision"]},
    )
    assert stale.status_code == 409


def test_agent_state_changes_require_owner_authentication(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    agent = owner_client.get("/agents", headers=headers).json()["agents"][0]
    response = owner_client.post(
        f"/agents/{agent['id']}/state",
        json={"target_state": "active", "expected_revision": agent["revision"]},
    )
    assert response.status_code == 401


def test_owner_can_bootstrap_one_draft_executive_orchestrator(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    first = owner_client.post("/agents/bootstrap-executive", headers=headers)
    assert first.status_code == 200
    assert first.json()["count"] == 1
    assert first.json()["agent"]["name"] == "Chief Executive Orchestrator"
    assert first.json()["agent"]["state"] == "draft"
    assert first.json()["execution_started"] is False

    second = owner_client.post("/agents/bootstrap-executive", headers=headers)
    assert second.status_code == 200
    assert second.json()["agent"]["id"] == first.json()["agent"]["id"]


def test_owner_can_bootstrap_500_specialist_profiles_as_drafts(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    first = owner_client.post("/agents/bootstrap-specialists", headers=headers)
    assert first.status_code == 200
    assert first.json()["count"] == 500
    assert first.json()["all_draft"] is True
    assert first.json()["execution_started"] is False

    second = owner_client.post("/agents/bootstrap-specialists", headers=headers)
    assert second.status_code == 200
    assert second.json()["count"] == 500

    listed = owner_client.get("/agents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 500
    assert all(item["state"] == "draft" for item in listed.json()["agents"])


def test_agent_registry_requires_owner_authentication(owner_client):
    response = owner_client.get("/agents", headers={"X-OpenCompany-API-Key": "wrong"})
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

    ready = owner_client.post(
        f"/work-items/{item_id}/transition", headers=headers,
        json={"target_state": "ready"},
    )
    assert ready.status_code == 200
    for state in ("queued", "in_progress"):
        blocked = owner_client.post(
            f"/work-items/{item_id}/transition", headers=headers,
            json={"target_state": state},
        )
        assert blocked.status_code == 409

    store = app.dependency_overrides[get_store]()
    from dataclasses import replace
    current = store.get_work_item(UUID(item_id))
    event_start = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="test.prepare_in_progress", subject_type="work_item",
        subject_id=item_id, outcome="recorded", correlation_id="api-review-test",
    )
    store.save_work_item_with_audit(replace(current, state=TaskState.IN_PROGRESS), event_start)
    deliverable = AgentDeliverable(
        id=uuid4(), work_item_id=UUID(item_id), role_key="market_intelligence_analyst",
        content="Review-ready draft", provider="fake", model="deterministic", cost_usd=0.0,
    )
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="agent",
        actor_id="test-agent", action="worker.deliverable_saved", subject_type="work_item",
        subject_id=item_id, outcome="recorded", correlation_id="api-review-test",
    )
    assert store.save_deliverable_with_audit(deliverable, event)
    direct_completion = owner_client.post(
        f"/work-items/{item_id}/transition", headers=headers,
        json={"target_state": "completed"},
    )
    assert direct_completion.status_code == 409
    reviewed = owner_client.post(
        f"/work-items/{item_id}/review", headers=headers,
        json={"approved": True, "rationale": "The draft meets the acceptance criteria."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["state"] == "completed"

    listed = owner_client.get("/work-items", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["state"] == "completed"

    audit = owner_client.get("/audit/verify", headers=headers)
    assert audit.status_code == 200
    assert audit.json() == {"event_count": 6, "chain_valid": True}


def test_owner_can_preview_manager_specialist_team_without_assigning_work(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Assess market demand",
        "objective": "Prepare a sourced market-demand assessment",
        "department": "intelligence-research",
    })
    assert created.status_code == 200
    response = owner_client.post(
        f"/work-items/{created.json()['item_id']}/delegation-preview",
        headers=headers,
        json={"required_capabilities": ["market", "researcher"], "max_specialists": 5},
    )
    assert response.status_code == 200
    plan = response.json()
    assert plan["manager"]["role_key"] == "market_intelligence_analyst"
    assert plan["mode"] == "specialist_team"
    assert len(plan["specialists"]) == 5
    assert len({item["team_key"] for item in plan["specialists"]}) == 1
    assert sum(item["supporting_member"] for item in plan["specialists"]) == 2
    assert plan["assignment_performed"] is False
    assert plan["execution_started"] is False


def test_delegation_preview_requires_owner_authentication(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Assess market demand",
        "objective": "Prepare a sourced market-demand assessment",
        "department": "intelligence-research",
    }).json()
    response = owner_client.post(
        f"/work-items/{created['item_id']}/delegation-preview",
        json={"required_capabilities": ["market"]},
    )
    assert response.status_code == 401


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
    assert ready.status_code == 409
    assert "prerequisite" in ready.json()["detail"].lower()
    queued = owner_client.post(
        f"/work-items/{second['item_id']}/transition", headers=headers,
        json={"target_state": "queued"},
    )
    assert queued.status_code == 409
    unchanged = owner_client.get("/work-items", headers=headers).json()["items"]
    assert next(item for item in unchanged if item["id"] == second["item_id"])["state"] == "draft"



def test_owner_approves_delegation_into_ready_tasks_without_queueing(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    assert owner_client.post("/agents/bootstrap", headers=headers).status_code == 200
    assert owner_client.post("/agents/bootstrap-specialists", headers=headers).status_code == 200
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Assess market demand",
        "objective": "Prepare a sourced market-demand assessment",
        "department": "intelligence-research",
    }).json()
    item_id = created["item_id"]
    proposal_response = owner_client.post(
        f"/work-items/{item_id}/delegation-proposals", headers=headers,
        json={"required_capabilities": ["market", "researcher"], "max_specialists": 5},
    )
    assert proposal_response.status_code == 200
    proposal = proposal_response.json()
    assert proposal["status"] == "draft"
    assert len(proposal["children"]) == 5
    assert proposal["queue_entries_created"] is False

    agents = {agent["id"]: agent for agent in owner_client.get("/agents", headers=headers).json()["agents"]}
    for child in proposal["children"]:
        agent = agents[child["assigned_agent_id"]]
        activated = owner_client.post(
            f"/agents/{agent['id']}/state", headers=headers,
            json={"target_state": "active", "expected_revision": agent["revision"]},
        )
        assert activated.status_code == 200

    manager = next(agent for agent in agents.values() if agent["role_key"] == "market_intelligence_analyst")
    manager_active = owner_client.post(
        f"/agents/{manager['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": manager["revision"]},
    )
    assert manager_active.status_code == 200

    # Simulate a process interruption after the first child insert but before
    # the proposal payload is updated. Approval must reuse this deterministic ID.
    runtime = owner_client.app.dependency_overrides[get_runtime]()
    first_child = proposal["children"][0]
    stable_orphan_id = __import__("uuid").uuid5(UUID(proposal["id"]), str(first_child["id"]))
    orphan = WorkItem(
        stable_orphan_id, first_child["title"], first_child["objective"],
        first_child["department"], TaskState.READY,
        runtime.store.get_work_item(UUID(item_id)).business_id, (),
        UUID(first_child["assigned_agent_id"]), first_child["role_key"],
    )
    runtime.store.create_work_item(orphan)

    approved = owner_client.post(
        f"/work-items/{item_id}/delegation-proposals/{proposal['id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["status"] == "approved"
    assert len(payload["materialized_work_items"]) == 5
    assert payload["materialized_work_items"][0]["id"] == str(stable_orphan_id)
    assert len(runtime.store.list_work_items()) == 6
    assert all(task["state"] == "ready" for task in payload["materialized_work_items"])
    assert payload["queue_entries_created"] is False
    assert payload["execution_started"] is False

    saved = owner_client.get(f"/work-items/{item_id}/delegation-proposals", headers=headers).json()
    assert saved["proposals"][0]["status"] == "approved"
    assert all(child["state"] == "approved" for child in saved["proposals"][0]["children"])
    audit = owner_client.get("/audit/verify", headers=headers)
    assert audit.status_code == 200 and audit.json()["chain_valid"] is True

    repeated = owner_client.post(
        f"/work-items/{item_id}/delegation-proposals/{proposal['id']}/approve",
        headers=headers,
    )
    assert repeated.status_code == 409


def test_delegation_approval_rejects_inactive_specialist_profiles(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    owner_client.post("/agents/bootstrap-specialists", headers=headers)
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Assess market demand", "objective": "Prepare a sourced assessment",
        "department": "intelligence-research",
    }).json()
    proposal = owner_client.post(
        f"/work-items/{created['item_id']}/delegation-proposals", headers=headers,
        json={"required_capabilities": ["market", "researcher"], "max_specialists": 5},
    ).json()
    response = owner_client.post(
        f"/work-items/{created['item_id']}/delegation-proposals/{proposal['id']}/approve",
        headers=headers,
    )
    assert response.status_code == 409
    assert "explicitly active" in response.json()["detail"]
    assert owner_client.get(f"/work-items/{created['item_id']}/delegation-proposals", headers=headers).json()["proposals"][0]["status"] == "draft"


def test_deliverables_endpoint_requires_owner_and_returns_persisted_records(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Prepare review draft",
        "objective": "Create a draft that remains private until owner review",
        "department": "intelligence-research",
    }).json()
    item_id = created["item_id"]
    response = owner_client.get(f"/work-items/{item_id}/deliverables", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"count": 0, "deliverables": []}
    unauthorized = owner_client.get(f"/work-items/{item_id}/deliverables")
    assert unauthorized.status_code == 401



def test_owner_session_login_is_rate_limited_after_five_failed_attempts(owner_client):
    api_module._clear_login_failures("testclient")
    for _ in range(4):
        response = owner_client.post("/auth/session", json={"api_key": "wrong-owner-key"})
        assert response.status_code == 401
    limited = owner_client.post("/auth/session", json={"api_key": "wrong-owner-key"})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    api_module._clear_login_failures("testclient")


def test_manager_proposal_api_accepts_expanded_specialist_team_limit():
    assert api_module.ManagerProposalInput().max_specialists == 15
    assert api_module.ManagerProposalInput(max_specialists=50).max_specialists == 50
    with pytest.raises(Exception):
        api_module.ManagerProposalInput(max_specialists=51)


def test_invalid_owner_api_key_headers_are_rate_limited(owner_client):
    api_module._clear_login_failures("testclient")
    for _ in range(4):
        response = owner_client.get("/agents", headers={"X-OpenCompany-API-Key": "wrong-owner-key"})
        assert response.status_code == 401
    limited = owner_client.get("/agents", headers={"X-OpenCompany-API-Key": "wrong-owner-key"})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    api_module._clear_login_failures("testclient")


def test_session_login_uses_http_only_cookie_and_restores_across_tabs(owner_client):
    login = owner_client.post("/auth/session", json={"api_key": "test-owner-key"})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    cookie = owner_client.cookies.get("opencompany_session")
    csrf_cookie = owner_client.cookies.get("opencompany_csrf")
    assert cookie and csrf_cookie
    set_cookies = "; ".join(login.headers.get_list("set-cookie"))
    assert "opencompany_session" in set_cookies
    assert "opencompany_csrf" in set_cookies
    assert set_cookies.lower().count("httponly") >= 2
    assert "samesite=strict" in set_cookies.lower()
    assert "max-age=604800" in set_cookies.lower()

    # Simulate closing/reopening the browser, then opening a second dashboard tab.
    with TestClient(app, base_url="https://testserver") as reopened, TestClient(app, base_url="https://testserver") as second_tab:
        for browser in (reopened, second_tab):
            browser.cookies.set("opencompany_session", cookie)
            browser.cookies.set("opencompany_csrf", csrf_cookie)
        status = reopened.get("/auth/session")
        assert status.status_code == 200 and status.json()["authenticated"] is True
        restored_csrf = status.json()["csrf_token"]
        assert restored_csrf == csrf
        second_status = second_tab.get("/auth/session")
        assert second_status.status_code == 200
        assert second_status.json()["csrf_token"] == restored_csrf

        blocked = reopened.post("/agents/bootstrap", json={})
        assert blocked.status_code == 401
        allowed = reopened.post(
            "/agents/bootstrap",
            headers={"X-CSRF-Token": restored_csrf, "Origin": "https://testserver"},
            json={},
        )
        assert allowed.status_code == 200
        logout = reopened.post(
            "/auth/logout",
            headers={"X-CSRF-Token": restored_csrf, "Origin": "https://testserver"},
        )
        assert logout.status_code == 200
        assert reopened.get("/agents").status_code == 401
        assert second_tab.get("/auth/session").status_code == 401



def test_durable_queue_lease_recovers_after_runtime_restart(tmp_path):
    database = str(tmp_path / "lease-recovery.sqlite3")
    runtime = create_runtime(database)
    agent_id, item_id = uuid4(), uuid4()
    role_key = "market_intelligence_analyst"
    item = WorkItem(
        id=item_id, title="Recover abandoned work", objective="Resume safely after worker crash",
        department="intelligence-research", state=TaskState.READY,
        assigned_agent_id=agent_id, assigned_role_key=role_key,
    )
    runtime.store.create_work_item(item)
    runtime.queue.admit(item_id, agent_id, role_key)
    first_lease = runtime.queue.claim(agent_id, role_key)
    assert first_lease is not None
    runtime.close()

    restarted = create_runtime(database)
    recovered = restarted.queue.recover_expired_leases(
        lease_seconds=1,
        now=datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1),
    )
    assert recovered == (item_id,)
    second_lease = restarted.queue.claim(agent_id, role_key)
    assert second_lease is not None
    assert second_lease.lease_id != first_lease.lease_id
    with pytest.raises(ValueError, match="stale"):
        restarted.queue.complete(first_lease)
    assert restarted.queue.complete(second_lease) is True
    assert restarted.queue.counts()["done"] == 1
    restarted.close()



def test_queue_admission_is_idempotent_and_failed_work_requires_explicit_retry():
    runtime = create_runtime(":memory:")
    agent_id, item_id = uuid4(), uuid4()
    role_key = "market_intelligence_analyst"
    item = WorkItem(
        id=item_id, title="Idempotent admission", objective="Avoid duplicate queue resets",
        department="intelligence-research", state=TaskState.READY,
        assigned_agent_id=agent_id, assigned_role_key=role_key,
    )
    runtime.store.create_work_item(item)
    assert runtime.queue.admit(item_id, agent_id, role_key) is True
    lease = runtime.queue.claim(agent_id, role_key)
    assert lease is not None
    with pytest.raises(ValueError, match="running or completed"):
        runtime.queue.admit(item_id, agent_id, role_key)
    runtime.queue.fail(lease)
    assert runtime.queue.admit(item_id, agent_id, role_key) is True
    assert runtime.queue.counts()["queued"] == 1
    assert runtime.queue.admit(item_id, agent_id, role_key) is False
    assert runtime.queue.counts()["queued"] == 1
    runtime.close()


def test_queue_rejects_mismatched_assigned_role():
    runtime = create_runtime(":memory:")
    agent_id, item_id = uuid4(), uuid4()
    item = WorkItem(
        id=item_id, title="Role mismatch", objective="Must not be routed to another role",
        department="intelligence-research", state=TaskState.READY,
        assigned_agent_id=agent_id, assigned_role_key="market_intelligence_analyst",
    )
    runtime.store.create_work_item(item)
    with pytest.raises(ValueError, match="assigned to this agent and role"):
        runtime.queue.admit(item_id, agent_id, "sales_representative")
    runtime.close()

def test_atomic_owner_queue_admission_and_worker_claim(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    owner_client.post("/agents/bootstrap-specialists", headers=headers)
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Research buyer demand",
        "objective": "Prepare a sourced buyer-demand report",
        "department": "intelligence-research",
    }).json()
    item_id = created["item_id"]
    proposal = owner_client.post(
        f"/work-items/{item_id}/delegation-proposals", headers=headers,
        json={"required_capabilities": ["market", "researcher"], "max_specialists": 5},
    ).json()
    agents = {a["id"]: a for a in owner_client.get("/agents", headers=headers).json()["agents"]}
    for child in proposal["children"]:
        agent = agents[child["assigned_agent_id"]]
        active = owner_client.post(
            f"/agents/{agent['id']}/state", headers=headers,
            json={"target_state": "active", "expected_revision": agent["revision"]},
        )
        assert active.status_code == 200
    manager = next(agent for agent in agents.values() if agent["role_key"] == "market_intelligence_analyst")
    manager_active = owner_client.post(
        f"/agents/{manager['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": manager["revision"]},
    )
    assert manager_active.status_code == 200
    approved = owner_client.post(
        f"/work-items/{item_id}/delegation-proposals/{proposal['id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    child = approved.json()["materialized_work_items"][0]
    child_id, agent_id = child["id"], child["assigned_agent_id"]
    runtime = app.dependency_overrides[get_runtime]()

    class ReadyFreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return (object(),)

    runtime.gateway = ReadyFreeGateway()
    queued = owner_client.post(f"/work-items/{child_id}/enqueue", headers=headers)
    assert queued.status_code == 200
    assert queued.json()["state"] == "queued"
    assert queued.json()["worker_started"] is False
    assert owner_client.get("/workers/queue", headers=headers).json()["counts"]["queued"] == 1

    lease = runtime.queue.claim(UUID(agent_id))
    assert lease is not None and str(lease.work_item_id) == child_id
    assert runtime.store.get_work_item(UUID(child_id)).state == TaskState.IN_PROGRESS
    assert runtime.store.verify_audit_chain()
    runtime.queue.complete(lease)


def test_queue_admission_rejects_unassigned_and_inactive_work(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Prepare research", "objective": "Create internal draft",
        "department": "intelligence-research",
    }).json()
    item_id = created["item_id"]
    owner_client.post(
        f"/work-items/{item_id}/transition", headers=headers,
        json={"target_state": "ready"},
    )
    rejected = owner_client.post(f"/work-items/{item_id}/enqueue", headers=headers)
    assert rejected.status_code == 409
    assert owner_client.get("/workers/queue", headers=headers).json()["total"] == 0


def test_owner_can_start_and_stop_worker_fleet_explicitly(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    status = owner_client.get("/workers/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["running"] is False
    runtime = app.dependency_overrides[get_runtime]()

    class NoFreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return ()

    runtime.gateway = NoFreeGateway()
    blocked = owner_client.post("/workers/start", headers=headers, json={})
    assert blocked.status_code == 503

    class ReadyFreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return (object(),)

    runtime.gateway = ReadyFreeGateway()
    started = owner_client.post("/workers/start", headers=headers, json={})
    assert started.status_code == 200 and started.json()["running"] is True
    stopped = owner_client.post("/workers/stop", headers=headers, json={})
    assert stopped.status_code == 200 and stopped.json()["running"] is False


class _ManagerPlannerFakeAdapter:
    def generate(self, request, *, model):
        return ModelResult(
            text='{"required_capabilities":["market","researcher"],"rationale":"The work requires market evidence and research synthesis, so one coherent intelligence team is appropriate."}',
            provider="unorouter", model=model, cost_usd=0.0,
        )


def test_active_department_manager_can_create_ai_proposal_without_execution(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    owner_client.post("/agents/bootstrap-specialists", headers=headers)
    runtime = app.dependency_overrides[get_runtime]()
    runtime.gateway = ModelGateway.configure(((
        ProviderPolicy(
            name="unorouter", model="test/free-model:free",
            billing_mode=BillingMode.FREE_CONFIRMED, max_cost_per_request_usd=0.0,
        ),
        _ManagerPlannerFakeAdapter(),
    ),))
    agents = owner_client.get("/agents", headers=headers).json()["agents"]
    manager = next(a for a in agents if a["role_key"] == "market_intelligence_analyst")
    activated = owner_client.post(
        f"/agents/{manager['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": manager["revision"]},
    )
    assert activated.status_code == 200
    item = owner_client.post("/work-items", headers=headers, json={
        "title": "Assess international buyer demand",
        "objective": "Create a sourced analysis of demand and competitor positioning",
        "department": "intelligence-research",
    }).json()
    response = owner_client.post(
        f"/work-items/{item['item_id']}/manager-proposal", headers=headers,
        json={"max_specialists": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["manager_ai"]["provider"] == "unorouter"
    assert payload["required_capabilities"] == ["market", "researcher"]
    assert payload["mode"] == "specialist_team"
    assert len(payload["proposal"]["children"]) == 5
    assert payload["owner_approval_required"] is True
    assert payload["assignment_performed"] is False
    assert payload["queue_entries_created"] is False
    assert payload["execution_started"] is False
    assert owner_client.get("/workers/queue", headers=headers).json()["total"] == 0


def test_ai_manager_proposal_requires_active_manager(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Research customer demand", "objective": "Assess market needs",
        "department": "intelligence-research",
    }).json()
    response = owner_client.post(
        f"/work-items/{created['item_id']}/manager-proposal", headers=headers,
        json={"max_specialists": 5},
    )
    assert response.status_code == 409
    assert "explicitly ACTIVE" in response.json()["detail"]


class _ExecutivePlannerFakeAdapter:
    def generate(self, request, *, model):
        return ModelResult(
            text='{"rationale":"Research demand first, then use the evidence to shape a product validation plan.","work_items":[{"department":"intelligence-research","title":"Map international buyer demand","objective":"Build a sourced demand and competitor report.","depends_on":[]},{"department":"product-innovation","title":"Prepare product validation plan","objective":"Translate the research findings into product tests and acceptance criteria.","depends_on":[0]}]}',
            provider="unorouter", model=model, cost_usd=0.0,
        )


def test_active_ceo_creates_atomic_draft_department_plan(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    provisioned = owner_client.post("/agents/bootstrap-executive", headers=headers)
    assert provisioned.status_code == 200
    ceo_id = provisioned.json()["agent"]["id"]
    ceo = next(a for a in owner_client.get("/agents", headers=headers).json()["agents"] if a["id"] == ceo_id)
    activated = owner_client.post(
        f"/agents/{ceo_id}/state", headers=headers,
        json={"target_state": "active", "expected_revision": ceo["revision"]},
    )
    assert activated.status_code == 200
    runtime = app.dependency_overrides[get_runtime]()
    runtime.gateway = ModelGateway.configure(((
        ProviderPolicy(
            name="unorouter", model="test/free-model:free",
            billing_mode=BillingMode.FREE_CONFIRMED, max_cost_per_request_usd=0.0,
        ),
        _ExecutivePlannerFakeAdapter(),
    ),))
    before = owner_client.get("/work-items", headers=headers).json()["count"]
    response = owner_client.post("/executive/plan", headers=headers, json={
        "title": "Build a new international digital business",
        "objective": "Research buyers, validate a product opportunity, and prepare a launch plan.",
        "business_id": "digital-products",
        "max_tasks": 8,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["created_count"] == 2
    assert payload["owner_review_required"] is True
    assert payload["queue_entries_created"] is False
    assert payload["execution_started"] is False
    assert all(item["state"] == "draft" for item in payload["items"])
    assert all(item["business_id"] == "digital-products" for item in payload["items"])
    assert payload["items"][1]["depends_on"] == [payload["items"][0]["id"]]
    after = owner_client.get("/work-items", headers=headers).json()["count"]
    assert after == before + 2
    assert runtime.store.verify_audit_chain()


def test_executive_plan_rejects_forward_or_unknown_dependencies(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    provisioned = owner_client.post("/agents/bootstrap-executive", headers=headers).json()
    ceo_id = provisioned["agent"]["id"]
    ceo = next(a for a in owner_client.get("/agents", headers=headers).json()["agents"] if a["id"] == ceo_id)
    owner_client.post(
        f"/agents/{ceo_id}/state", headers=headers,
        json={"target_state": "active", "expected_revision": ceo["revision"]},
    )
    runtime = app.dependency_overrides[get_runtime]()
    class InvalidPlanAdapter:
        def generate(self, request, *, model):
            return ModelResult(
                text='{"rationale":"bad graph","work_items":[{"department":"intelligence-research","title":"First","objective":"First task","depends_on":[1]}]}',
                provider="unorouter", model=model, cost_usd=0.0,
            )
    runtime.gateway = ModelGateway.configure(((
        ProviderPolicy("unorouter","test/free-model:free",BillingMode.FREE_CONFIRMED,0.0),
        InvalidPlanAdapter(),
    ),))
    response = owner_client.post("/executive/plan", headers=headers, json={
        "title": "Invalid plan", "objective": "Create a plan", "max_tasks": 3,
    })
    assert response.status_code == 422
    assert owner_client.get("/work-items", headers=headers).json()["count"] == 0


class _LearningPlannerFakeAdapter:
    def generate(self, request, *, model):
        return ModelResult(
            text='{"role_key":"market_intelligence_analyst","note":"Verify publication dates and prefer current primary sources for demand claims.","rationale":"The reviewed report identified inconsistent source freshness.","expected_measurement":"Reduce stale-source findings in the next five market reports.","risk_level":"low"}',
            provider="unorouter", model=model, cost_usd=0.0,
        )


def test_review_outcome_generates_owner_approved_learning_note(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post("/work-items", headers=headers, json={
        "title": "Review market evidence", "objective": "Prepare a sourced buyer-demand report",
        "department": "intelligence-research",
    }).json()
    item_id = UUID(created["item_id"])
    store = app.dependency_overrides[get_store]()
    from dataclasses import replace
    item = store.get_work_item(item_id)
    store.save_work_item_with_audit(replace(item, state=TaskState.IN_PROGRESS), AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="test.start", subject_type="work_item",
        subject_id=str(item_id), outcome="recorded", correlation_id="learning-test",
    ))
    deliverable = AgentDeliverable(
        id=uuid4(), work_item_id=item_id, role_key="market_intelligence_analyst",
        content="Buyer demand appears strong. Sources were not all current.",
        provider="fake", model="deterministic", cost_usd=0.0,
    )
    store.save_deliverable_with_audit(deliverable, AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="agent",
        actor_id="test-agent", action="worker.deliverable_saved",
        subject_type="work_item", subject_id=str(item_id),
        outcome="recorded", correlation_id="learning-test",
    ))
    reviewed = owner_client.post(
        f"/work-items/{item_id}/review", headers=headers,
        json={"approved": True, "rationale": "Useful report; source freshness should improve."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["evaluation_recorded"] is True
    evaluation_id = reviewed.json()["evaluation_id"]

    runtime = app.dependency_overrides[get_runtime]()
    runtime.gateway = ModelGateway.configure(((
        ProviderPolicy("unorouter", "test/free-model:free", BillingMode.FREE_CONFIRMED, 0.0),
        _LearningPlannerFakeAdapter(),
    ),))
    proposed = owner_client.post("/learning/ai-proposals", headers=headers, json={
        "evaluation_ids": [evaluation_id],
    })
    assert proposed.status_code == 200
    proposal_id = proposed.json()["id"]
    assert proposed.json()["owner_approval_required"] is True
    assert proposed.json()["note_applied"] is False

    decision = owner_client.post(
        f"/learning/proposals/{proposal_id}/decision", headers=headers,
        json={"approved": True, "rationale": "Approved for future market research work."},
    )
    assert decision.status_code == 200
    applied = owner_client.post(
        f"/learning/proposals/{proposal_id}/apply-note", headers=headers, json={},
    )
    assert applied.status_code == 200
    assert applied.json()["state"] == "implemented"
    notes = owner_client.get(
        "/learning/notes/market_intelligence_analyst", headers=headers,
    ).json()
    assert notes["count"] == 1
    assert "publication dates" in notes["notes"][0]["note"]
    assert runtime.store.verify_audit_chain()


class _CodeEvolutionFakeClient:
    repository = "owner/repo"
    base_branch = "clean-room-rebuild"
    def read_files(self, paths):
        return {path: "# existing source\\n" for path in paths}
    def create_pull_request(self, *, title, summary, files):
        return GitHubPullRequest(88, "https://github.com/owner/repo/pull/88", "feat/opencompany-evolution-test", "commit88", title)


class _CodeEvolutionFakeAdapter:
    def generate(self, request, *, model):
        return ModelResult(
            text='{"title":"Improve source reliability","summary":"Add a bounded validation improvement.","files":[{"path":"src/opencompany_core/sample.py","content":"VALUE = 2\\n"}]}',
            provider="unorouter", model=model, cost_usd=0.0,
        )


def test_owner_can_generate_isolated_code_evolution_draft_pr(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    runtime.github_evolution = _CodeEvolutionFakeClient()
    runtime.github_evolution_tested_at = "2026-11-11T00:00:00+00:00"
    runtime.gateway = ModelGateway.configure(((
        ProviderPolicy("unorouter", "test/free-model:free", BillingMode.FREE_CONFIRMED, 0.0),
        _CodeEvolutionFakeAdapter(),
    ),))
    runtime.gateway.set_usage_recorder(runtime.usage.record)
    response = owner_client.post("/code-evolution/proposals", headers=headers, json={
        "problem": "Improve a source module with a small, tested reliability change.",
        "file_paths": ["src/opencompany_core/sample.py"],
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["pull_request_number"] == 88
    assert payload["draft"] is True
    assert payload["merged"] is False
    assert payload["deployed"] is False
    assert payload["owner_merge_review_required"] is True
    assert runtime.store.verify_audit_chain()


def test_code_evolution_config_status_does_not_expose_credentials(owner_client):
    runtime = app.dependency_overrides[get_runtime]()
    runtime.github_evolution = _CodeEvolutionFakeClient()
    runtime.github_evolution_tested_at = "2026-11-11T00:00:00+00:00"
    response = owner_client.get("/code-evolution/config-status", headers={"X-OpenCompany-API-Key": "test-owner-key"})
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert "token" not in response.text.lower()



def test_owner_cookie_session_rejects_cross_origin_write_even_with_csrf(owner_client):
    login = owner_client.post("/auth/session", json={"api_key": "test-owner-key"})
    assert login.status_code == 200
    response = owner_client.post(
        "/agents/bootstrap",
        headers={
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": "https://attacker.example",
        },
        json={},
    )
    assert response.status_code == 403
    assert "same origin" in response.json()["detail"]


def test_owner_cookie_session_requires_origin_on_mutating_requests(owner_client):
    login = owner_client.post("/auth/session", json={"api_key": "test-owner-key"})
    assert login.status_code == 200
    response = owner_client.post(
        "/agents/bootstrap",
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
        json={},
    )
    assert response.status_code == 403


def test_runtime_repositories_share_one_sqlite_connection_and_lock(owner_client):
    runtime = app.dependency_overrides[get_runtime]()
    connection = runtime.store._connection
    lock = runtime.store._lock
    assert runtime.queue._db is connection
    assert runtime.delegations._db is connection
    assert runtime.sessions._db is connection
    assert runtime.handoffs._db is connection
    assert runtime.learning._db is connection
    assert runtime.usage._db is connection
    assert runtime.queue._lock is lock
    assert runtime.delegations._lock is lock
    assert runtime.sessions._lock is lock
    assert runtime.handoffs._lock is lock
    assert runtime.learning._lock is lock
    assert runtime.usage._lock is lock


def test_end_to_end_owner_approved_task_runs_to_review_and_learning(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    owner_client.post("/agents/bootstrap-specialists", headers=headers)
    parent = owner_client.post("/work-items", headers=headers, json={
        "title": "Assess overseas market demand",
        "objective": "Prepare an evidence-backed internal market assessment",
        "department": "intelligence-research",
    }).json()
    parent_id = parent["item_id"]

    proposal_response = owner_client.post(
        f"/work-items/{parent_id}/delegation-proposals",
        headers=headers,
        json={"required_capabilities": ["market", "researcher"], "max_specialists": 1},
    )
    assert proposal_response.status_code == 200
    proposal = proposal_response.json()
    profiles = {
        agent["id"]: agent
        for agent in owner_client.get("/agents", headers=headers).json()["agents"]
    }
    for child in proposal["children"]:
        profile = profiles[child["assigned_agent_id"]]
        activated = owner_client.post(
            f"/agents/{profile['id']}/state",
            headers=headers,
            json={"target_state": "active", "expected_revision": profile["revision"]},
        )
        assert activated.status_code == 200
    manager = next(agent for agent in profiles.values() if agent["role_key"] == "market_intelligence_analyst")
    manager_active = owner_client.post(
        f"/agents/{manager['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": manager["revision"]},
    )
    assert manager_active.status_code == 200

    approved = owner_client.post(
        f"/work-items/{parent_id}/delegation-proposals/{proposal['id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    child_task = approved.json()["materialized_work_items"][0]
    child_record = next(
        child for child in proposal["children"]
        if child["assigned_agent_id"] == child_task["assigned_agent_id"]
    )
    agent_id = UUID(child_task["assigned_agent_id"])
    role_key = child_record["role_key"]

    # Without a confirmed free provider, the API must not admit work that
    # cannot execute. A deterministic test gateway then exercises the path.
    runtime = app.dependency_overrides[get_runtime]()

    class NoFreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return ()

    runtime.gateway = NoFreeGateway()
    blocked = owner_client.post(
        f"/work-items/{child_task['id']}/enqueue", headers=headers,
    )
    assert blocked.status_code == 503

    class ReadyFreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return (object(),)

    runtime.gateway = ReadyFreeGateway()
    queued = owner_client.post(
        f"/work-items/{child_task['id']}/enqueue", headers=headers,
    )
    assert queued.status_code == 200
    assert queued.json()["state"] == "queued"

    class DeterministicExecutor:
        def execute(self, requested_role, item, **kwargs):
            return AgentDeliverable(
                id=uuid4(), work_item_id=item.id, role_key=requested_role,
                content="Evidence-backed market research draft for owner review.",
                provider="test", model="deterministic", cost_usd=0.0,
            )

    runtime.worker.executor = DeterministicExecutor()
    result = runtime.worker.run_once(agent_id, role_key)
    assert result == "completed_review_required"
    assert runtime.store.get_work_item(UUID(child_task["id"])).state == TaskState.REVIEW
    assert runtime.queue.counts().get("done") == 1

    deliverables = owner_client.get(
        f"/work-items/{child_task['id']}/deliverables", headers=headers,
    )
    assert deliverables.status_code == 200
    assert deliverables.json()["count"] == 1
    reviewed = owner_client.post(
        f"/work-items/{child_task['id']}/review",
        headers=headers,
        json={"approved": True, "rationale": "The draft meets the acceptance criteria."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["state"] == "completed"
    assert reviewed.json()["evaluation_recorded"] is True

    # The approved manager synthesis parent is now READY only after every
    # child is owner-approved, and it receives the specialist deliverable IDs.
    manager_parent = runtime.store.get_work_item(UUID(parent_id))
    assert manager_parent.state == TaskState.READY
    assert manager_parent.assigned_agent_id == UUID(manager["id"])
    assert manager_parent.depends_on == (UUID(child_task["id"]),)

    manager_queued = owner_client.post(
        f"/work-items/{parent_id}/enqueue", headers=headers,
    )
    assert manager_queued.status_code == 200
    manager_result = runtime.worker.run_once(
        UUID(manager["id"]), "market_intelligence_analyst",
    )
    assert manager_result == "completed_review_required"
    assert runtime.store.get_work_item(UUID(parent_id)).state == TaskState.REVIEW
    manager_deliverables = owner_client.get(
        f"/work-items/{parent_id}/deliverables", headers=headers,
    )
    assert manager_deliverables.status_code == 200
    assert manager_deliverables.json()["count"] == 1
    manager_review = owner_client.post(
        f"/work-items/{parent_id}/review", headers=headers,
        json={"approved": True, "rationale": "The manager synthesis incorporates the approved specialist result."},
    )
    assert manager_review.status_code == 200
    assert manager_review.json()["state"] == "completed"
    assert runtime.store.verify_audit_chain() is True


def test_worker_autostart_flag_starts_fleet_during_api_startup(monkeypatch):
    calls = []

    class Fleet:
        def start(self):
            calls.append("started")
            return True

    class Gateway:
        ready = False

        def eligible_providers(self, *, request_budget_usd=0.0):
            return (object(),) if self.ready else ()

    class Runtime:
        fleet = Fleet()
        gateway = Gateway()

    runtime = Runtime()
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "true")
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    monkeypatch.setattr(api_module, "_default_runtime", lambda: runtime)

    api_module.initialize_autonomous_runtime()
    assert calls == []

    runtime.gateway.ready = True
    api_module.initialize_autonomous_runtime()
    assert calls == ["started"]


def test_runtime_factory_never_starts_background_workers(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "true")
    runtime = create_runtime(str(tmp_path / "runtime-factory.sqlite3"))
    try:
        assert runtime.fleet.status().running is False
    finally:
        runtime.close()



def test_readiness_checks_persistent_storage_without_requiring_provider(owner_client):
    response = owner_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "opencompany-core",
        "storage": "ok",
        "worker_fleet_running": False,
        "provider_required_for_readiness": False,
    }


def test_readiness_requires_owner_runtime_configuration(monkeypatch):
    monkeypatch.delenv("OPENCOMPANY_OWNER_API_KEY", raising=False)
    response = client.get("/ready")
    assert response.status_code == 503



def test_model_usage_summary_is_owner_authenticated_and_secret_free(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    assert runtime.usage.record({
        "request_id": "usage-test-1",
        "work_item_id": str(uuid4()),
        "role_key": "market_intelligence_analyst",
        "provider": "unorouter",
        "model": "vendor/free-model:free",
        "input_tokens": 120,
        "output_tokens": 45,
        "cost_usd": 0.0,
    }) is True
    response = owner_client.get("/usage/model", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_count"] == 1
    assert payload["total_cost_usd"] == 0.0
    assert payload["total_input_tokens"] == 120
    assert payload["total_output_tokens"] == 45
    assert payload["events"][0]["provider"] == "unorouter"
    assert "api_key" not in response.text.lower()
    denied = owner_client.get("/usage/model")
    assert denied.status_code == 401


def test_auto_queue_runs_only_after_owner_approval_and_zero_cost_provider_readiness(owner_client, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_AUTO_QUEUE_APPROVED_WORK", "true")
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    owner_client.post("/agents/bootstrap", headers=headers)
    owner_client.post("/agents/bootstrap-specialists", headers=headers)
    parent = owner_client.post("/work-items", headers=headers, json={
        "title": "Automate manager-led market assessment",
        "objective": "Complete specialist research and consolidate it for owner review",
        "department": "intelligence-research",
    }).json()
    proposal = owner_client.post(
        f"/work-items/{parent['item_id']}/delegation-proposals",
        headers=headers,
        json={"required_capabilities": ["market", "researcher"], "max_specialists": 1},
    ).json()
    profiles = {
        agent["id"]: agent
        for agent in owner_client.get("/agents", headers=headers).json()["agents"]
    }
    child = proposal["children"][0]
    specialist = profiles[child["assigned_agent_id"]]
    manager = next(value for value in profiles.values() if value["role_key"] == "market_intelligence_analyst")
    for profile in (specialist, manager):
        response = owner_client.post(
            f"/agents/{profile['id']}/state", headers=headers,
            json={"target_state": "active", "expected_revision": profile["revision"]},
        )
        assert response.status_code == 200

    runtime = app.dependency_overrides[get_runtime]()

    class ReadyFreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            assert request_budget_usd == 0.0
            return ("unorouter-free",)

    class DeterministicExecutor:
        def execute(self, requested_role, item, **kwargs):
            return AgentDeliverable(
                id=uuid4(), work_item_id=item.id, role_key=requested_role,
                content=f"Approved-input draft from {requested_role}.",
                provider="test", model="deterministic", cost_usd=0.0,
            )

    runtime.gateway = ReadyFreeGateway()
    runtime.worker.executor = DeterministicExecutor()
    approved = owner_client.post(
        f"/work-items/{parent['item_id']}/delegation-proposals/{proposal['id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    payload = approved.json()
    child_id = payload["materialized_work_items"][0]["id"]
    assert payload["auto_queue"]["enabled"] is True
    assert payload["auto_queue"]["provider_ready"] is True
    assert payload["auto_queue"]["queued_work_item_ids"] == [child_id]
    assert payload["queue_entries_created"] is True
    assert runtime.queue.counts()["queued"] == 1

    assert runtime.worker.run_once(UUID(specialist["id"]), child["role_key"]) == "completed_review_required"
    child_review = owner_client.post(
        f"/work-items/{child_id}/review", headers=headers,
        json={"approved": True, "rationale": "Specialist evidence is accepted for manager synthesis."},
    )
    assert child_review.status_code == 200
    assert child_review.json()["auto_queue"]["queued_work_item_ids"] == [parent["item_id"]]
    assert runtime.queue.counts()["queued"] == 1

    assert runtime.worker.run_once(UUID(manager["id"]), "market_intelligence_analyst") == "completed_review_required"
    manager_review = owner_client.post(
        f"/work-items/{parent['item_id']}/review", headers=headers,
        json={"approved": True, "rationale": "Manager synthesis accepted."},
    )
    assert manager_review.status_code == 200
    assert manager_review.json()["state"] == "completed"


class _UnavailableUnoRouterAdapter:
    def generate(self, request, *, model):
        raise ProviderUnavailable("UnoRouter returned HTTP 401.")


class _SuccessfulUnoRouterAdapter:
    def generate(self, request, *, model):
        return ModelResult(
            text="OPENCOMPANY_UNOROUTER_OK", provider="unorouter",
            model=model, cost_usd=0.0, input_tokens=5, output_tokens=4,
        )


def test_unorouter_test_reports_provider_failure_without_mislabeling_auth(owner_client, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "false")
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    runtime.gateway = ModelGateway.configure((
        (ProviderPolicy("unorouter", "test/free-model:free", BillingMode.FREE_CONFIRMED, 0.0),
         _UnavailableUnoRouterAdapter()),
    ))
    runtime.gateway.set_usage_recorder(runtime.usage.record)

    started = owner_client.post("/settings/providers/unorouter/test", headers=headers, json={})
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    result = owner_client.get(f"/settings/providers/unorouter/test/{job_id}", headers=headers)

    assert result.status_code == 200
    assert result.json()["status"] == "failed"
    assert result.json()["error"] == (
        "UnoRouter test failed safely: All eligible providers were unavailable: "
        "unorouter: UnoRouter returned HTTP 401.. No paid fallback was attempted."
    )
    assert result.json()["paid_fallback"] is False
    assert runtime.unorouter_tested_at is None
    assert runtime.fleet.status().running is False


def test_unorouter_test_succeeds_with_zero_cost_and_polls_result(owner_client, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "false")
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    runtime.gateway = ModelGateway.configure((
        (ProviderPolicy("unorouter", "test/free-model:free", BillingMode.FREE_CONFIRMED, 0.0),
         _SuccessfulUnoRouterAdapter()),
    ))
    runtime.gateway.set_usage_recorder(runtime.usage.record)

    started = owner_client.post("/settings/providers/unorouter/test", headers=headers, json={})
    assert started.status_code == 202
    result = owner_client.get(
        f"/settings/providers/unorouter/test/{started.json()['job_id']}", headers=headers,
    )

    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "succeeded"
    assert payload["success"] is True
    assert payload["provider"] == "unorouter"
    assert payload["model"] == "test/free-model:free"
    assert payload["cost_usd"] == 0.0
    assert payload["output_preview"] == "OPENCOMPANY_UNOROUTER_OK"
    assert payload["worker_autostart_enabled"] is False
    assert payload["worker_started"] is False
    assert payload["paid_fallback"] is False
    assert runtime.unorouter_tested_at is not None
    assert runtime.fleet.status().running is False



def test_saved_unorouter_catalogue_refresh_uses_server_key_without_reentry(owner_client, monkeypatch):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    saved = {"api_key": "saved-inference-key-never-return-this", "model": "unorouter/free-catalog:free"}
    monkeypatch.setattr(runtime.secret_vault, "get", lambda name: saved if name == "unorouter" else None)
    monkeypatch.setattr(
        api_module, "discover_free_models",
        lambda api_key, force_refresh=False: ("alpha:free", "beta:free") if api_key == saved["api_key"] and force_refresh else (),
    )

    response = owner_client.get("/settings/providers/unorouter/models", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["routing_mode"] == "automatic_all_free_models"
    assert payload["models"] == ["alpha:free", "beta:free"]
    assert payload["paid_fallback"] is False
    assert "saved-inference-key-never-return-this" not in response.text


def test_owner_work_item_workflow_view_reports_lifecycle_and_next_action(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post(
        "/work-items",
        headers=headers,
        json={
            "title": "Workflow visibility check",
            "objective": "Verify the owner can inspect the full internal task lifecycle.",
            "department": "intelligence-research",
            "depends_on": [],
        },
    )
    assert created.status_code == 200
    item_id = created.json()["item_id"]

    response = owner_client.get(f"/work-items/{item_id}/workflow", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["work_item"]["id"] == item_id
    assert payload["work_item"]["state"] == "draft"
    assert payload["next_action"] == "owner_review_and_mark_ready"
    assert payload["prerequisites"] == []
    assert payload["dependents"] == []
    assert payload["queue"] is None
    assert payload["deliverables"] == []
    assert payload["counts"]["deliverables"] == 0


def test_work_item_workflow_view_requires_owner_authentication(owner_client):
    created = owner_client.post(
        "/work-items",
        headers={"X-OpenCompany-API-Key": "test-owner-key"},
        json={
            "title": "Private workflow",
            "objective": "Check private workflow visibility.",
            "department": "intelligence-research",
            "depends_on": [],
        },
    )
    assert created.status_code == 200

    response = owner_client.get(f"/work-items/{created.json()['item_id']}/workflow")

    assert response.status_code == 401


def test_running_work_item_cannot_be_cancelled_without_queue_aware_recovery(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post(
        "/work-items",
        headers=headers,
        json={
            "title": "Running task cancellation guard",
            "objective": "Ensure state-only cancellation cannot orphan a worker lease.",
            "department": "intelligence-research",
            "depends_on": [],
        },
    )
    assert created.status_code == 200
    item_id = created.json()["item_id"]
    runtime = app.dependency_overrides[get_runtime]()
    with runtime.store._lock:
        runtime.store._connection.execute(
            "UPDATE work_items SET state=? WHERE id=?",
            (TaskState.IN_PROGRESS.value, item_id),
        )

    response = owner_client.post(
        f"/work-items/{item_id}/transition",
        headers=headers,
        json={"target_state": "cancelled"},
    )

    assert response.status_code == 409
    assert "queue-aware cancellation" in response.json()["detail"]


def test_work_items_are_created_and_listed_inside_selected_business_unit(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    agency = owner_client.post(
        "/work-items", headers=headers,
        json={
            "title": "Agency supplier qualification",
            "objective": "Assess a third-party supplier.",
            "department": "intelligence-research",
            "business_id": "physical-agency",
        },
    )
    assert agency.status_code == 200
    item_id = agency.json()["item_id"]
    assert agency.json()["business_id"] == "physical-agency"

    agency_list = owner_client.get("/work-items?business_id=physical-agency", headers=headers)
    digital_list = owner_client.get("/work-items?business_id=digital-products", headers=headers)
    workflow = owner_client.get(f"/work-items/{item_id}/workflow", headers=headers)

    assert agency_list.status_code == 200
    assert [item["id"] for item in agency_list.json()["items"]] == [item_id]
    assert digital_list.status_code == 200
    assert all(item["business_id"] == "digital-products" for item in digital_list.json()["items"])
    assert workflow.status_code == 200
    assert workflow.json()["work_item"]["business_id"] == "physical-agency"

    cross_business = owner_client.post(
        "/work-items", headers=headers,
        json={
            "title": "Cross-business dependency",
            "objective": "This must be rejected.",
            "department": "intelligence-research",
            "business_id": "digital-products",
            "depends_on": [item_id],
        },
    )
    assert cross_business.status_code == 422


def test_unknown_business_unit_is_rejected(owner_client):
    response = owner_client.post(
        "/work-items",
        headers={"X-OpenCompany-API-Key": "test-owner-key"},
        json={
            "title": "Unknown business",
            "objective": "Must not be persisted.",
            "department": "intelligence-research",
            "business_id": "unregistered-business",
        },
    )
    assert response.status_code == 422


def test_finance_ledger_routes_require_owner_and_never_initiate_payments(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    payload = {
        "business_id": "physical-agency",
        "entry_type": "expense",
        "amount_minor": 4999,
        "currency": "USD",
        "description": "Recorded expense request; no purchase made",
        "confirm_owner_record": True,
    }
    unauthorized = owner_client.post("/finance/entries", json=payload)
    assert unauthorized.status_code == 401

    missing_confirmation = owner_client.post(
        "/finance/entries", headers=headers,
        json={**payload, "confirm_owner_record": False},
    )
    assert missing_confirmation.status_code == 422

    created = owner_client.post("/finance/entries", headers=headers, json=payload)
    assert created.status_code == 200
    result = created.json()
    assert result["recorded"] is True
    assert result["external_payment_initiated"] is False
    assert result["spending_authorized"] is False

    entry_id = result["entry_id"]
    review = owner_client.post(
        f"/finance/entries/{entry_id}/review", headers=headers,
        json={"action": "owner_approved", "rationale": "Approved as an internal record only.",
              "confirm_owner_decision": True},
    )
    assert review.status_code == 200
    assert review.json()["external_payment_initiated"] is False
    assert review.json()["spending_authorized"] is False
    duplicate_review = owner_client.post(
        f"/finance/entries/{entry_id}/review", headers=headers,
        json={"action": "owner_rejected", "rationale": "Conflicting second decision",
              "confirm_owner_decision": True},
    )
    assert duplicate_review.status_code == 422

    listed = owner_client.get("/finance/entries?business_id=physical-agency", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["entries"][0]["latest_review_action"] == "owner_approved"


def test_finance_review_rejects_missing_owner_confirmation(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    created = owner_client.post("/finance/entries", headers=headers, json={
        "business_id": "physical-brand", "entry_type": "revenue",
        "amount_minor": 100, "currency": "PKR", "description": "Test revenue",
        "confirm_owner_record": True,
    })
    assert created.status_code == 200
    response = owner_client.post(
        f"/finance/entries/{created.json()['entry_id']}/review",
        headers=headers,
        json={"action": "owner_verified", "rationale": "test",
              "confirm_owner_decision": False},
    )
    assert response.status_code == 422



def test_business_credentials_are_owner_scoped_encrypted_and_never_returned(owner_client, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-business-credential-encryption-key-32")
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    payload = {
        "credential_key": "marketplace-api",
        "secret": {"api_key": "do-not-return-this-secret"},
        "confirm_owner_storage": True,
    }
    unauthorized = owner_client.post(
        "/business-units/physical-agency/credentials", json=payload
    )
    assert unauthorized.status_code == 401
    missing_confirmation = owner_client.post(
        "/business-units/physical-agency/credentials", headers=headers,
        json={**payload, "confirm_owner_storage": False},
    )
    assert missing_confirmation.status_code == 422
    stored = owner_client.post(
        "/business-units/physical-agency/credentials", headers=headers, json=payload
    )
    assert stored.status_code == 200
    assert stored.json()["external_connection_attempted"] is False
    assert "do-not-return-this-secret" not in stored.text
    status = owner_client.get(
        "/business-units/physical-agency/credentials", headers=headers
    )
    assert status.status_code == 200
    assert status.json()["credentials"][0]["credential_key"] == "marketplace-api"
    assert "do-not-return-this-secret" not in status.text
    isolated = owner_client.get(
        "/business-units/physical-brand/credentials", headers=headers
    )
    assert isolated.status_code == 200
    assert isolated.json()["count"] == 0
    deleted = owner_client.request(
        "DELETE", "/business-units/physical-agency/credentials/marketplace-api",
        headers=headers, json={"confirm_owner_deletion": True},
    )
    assert deleted.status_code == 200




def test_business_integration_registry_requires_owner_and_never_connects(owner_client, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-business-credential-encryption-key-32")
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    credential = owner_client.post(
        "/business-units/physical-agency/credentials", headers=headers,
        json={"credential_key": "marketplace-api", "secret": {"api_key": "integration-secret"},
              "confirm_owner_storage": True},
    )
    assert credential.status_code == 200
    payload = {
        "provider_key": "marketplace-x", "display_name": "Marketplace X",
        "credential_key": "marketplace-api", "permissions": ["catalog:read", "orders:read"],
        "rationale": "Read-only marketplace discovery",
        "confirm_owner_registration": True,
    }
    unauthorized = owner_client.post(
        "/business-units/physical-agency/integrations", json=payload
    )
    assert unauthorized.status_code == 401
    unconfirmed = owner_client.post(
        "/business-units/physical-agency/integrations", headers=headers,
        json={**payload, "confirm_owner_registration": False},
    )
    assert unconfirmed.status_code == 422
    registered = owner_client.post(
        "/business-units/physical-agency/integrations", headers=headers, json=payload
    )
    assert registered.status_code == 200
    body = registered.json()
    assert body["integration"]["status"] == "pending_review"
    assert body["external_connection_attempted"] is False
    assert "integration-secret" not in registered.text
    listed = owner_client.get(
        "/business-units/physical-agency/integrations", headers=headers
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["external_connections_enabled"] is False
    isolated = owner_client.get(
        "/business-units/physical-brand/integrations", headers=headers
    )
    assert isolated.status_code == 200
    assert isolated.json()["count"] == 0
    integration_id = body["integration"]["integration_id"]
    history = owner_client.get(
        f"/business-units/physical-agency/integrations/{integration_id}/events",
        headers=headers,
    )
    assert history.status_code == 200
    assert history.json()["events"][0]["action"] == "registered"
    removed = owner_client.request(
        "DELETE", "/business-units/physical-agency/credentials/marketplace-api",
        headers=headers, json={"confirm_owner_deletion": True},
    )
    assert removed.status_code == 200
    after_removal = owner_client.get(
        "/business-units/physical-agency/integrations", headers=headers
    )
    assert after_removal.status_code == 200
    assert after_removal.json()["integrations"][0]["credential_available"] is False




def test_business_memory_api_requires_owner_confirmation_and_isolates_units(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    payload = {
        "memory_key": "buyer-profile", "category": "strategy",
        "content": "International wholesale buyers", "source": "owner research note",
        "confirm_owner_write": True,
    }
    unauthorized = owner_client.post("/business-units/physical-agency/memory", json=payload)
    assert unauthorized.status_code == 401
    unconfirmed = owner_client.post(
        "/business-units/physical-agency/memory", headers=headers,
        json={**payload, "confirm_owner_write": False},
    )
    assert unconfirmed.status_code == 422
    saved = owner_client.post("/business-units/physical-agency/memory", headers=headers, json=payload)
    assert saved.status_code == 200
    assert saved.json()["memory"]["revision"] == 1
    assert saved.json()["agent_writes_enabled"] is False
    listed = owner_client.get("/business-units/physical-agency/memory", headers=headers)
    assert listed.status_code == 200 and listed.json()["count"] == 1
    isolated = owner_client.get("/business-units/physical-brand/memory", headers=headers)
    assert isolated.status_code == 200 and isolated.json()["count"] == 0
    history = owner_client.get(
        "/business-units/physical-agency/memory/buyer-profile/history", headers=headers
    )
    assert history.status_code == 200 and len(history.json()["history"]) == 1
    forgotten = owner_client.request(
        "DELETE", "/business-units/physical-agency/memory/buyer-profile", headers=headers,
        json={"confirm_owner_forget": True},
    )
    assert forgotten.status_code == 200
    assert forgotten.json()["historical_versions_retained"] is True
    after = owner_client.get("/business-units/physical-agency/memory", headers=headers)
    assert after.status_code == 200 and after.json()["count"] == 0



def test_business_asset_upload_is_owner_confirmed_private_and_unavailable(owner_client, tmp_path):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    payload_bytes = b"glTF" + b"\x02\x00\x00\x00" + b"\x18\x00\x00\x00" + b"test"
    digest = hashlib.sha256(payload_bytes).hexdigest()
    declared = owner_client.post("/business-units/digital-products/assets", headers=headers, json={
        "asset_key": "demo-model", "title": "Demo model", "asset_type": "3d-model",
        "filename": "demo.glb", "media_type": "model/gltf-binary",
        "checksum_sha256": digest, "byte_size": len(payload_bytes),
        "source": "owner upload", "confirm_owner_declaration": True,
    })
    assert declared.status_code == 200
    asset_id = declared.json()["asset"]["asset_id"]
    runtime.asset_storage = PrivateFilesystemAssetStorage(tmp_path / "private-assets")

    no_confirmation = owner_client.put(
        f"/business-units/digital-products/assets/{asset_id}/content",
        headers={**headers, "Content-Type": "model/gltf-binary"},
        content=payload_bytes,
    )
    assert no_confirmation.status_code == 422

    uploaded = owner_client.put(
        f"/business-units/digital-products/assets/{asset_id}/content",
        headers={**headers, "Content-Type": "model/gltf-binary", "X-Confirm-Owner-Upload": "true"},
        content=payload_bytes,
    )
    assert uploaded.status_code == 200
    result = uploaded.json()
    assert result["checksum_verified"] is True
    assert result["malware_scan_completed"] is False
    assert result["download_enabled"] is False
    assert "storage_key" not in result["asset"]
    listed = owner_client.get("/business-units/digital-products/assets", headers=headers).json()["assets"][0]
    assert listed["storage_state"] == "private_stored_unscanned"
    assert listed["status"] == "pending_scan"

    class CleanScanner:
        def scan(self, chunks):
            scanned = b"".join(chunks)
            return {
                "status": "clean", "scanner_key": "test-clamav",
                "checksum_sha256": hashlib.sha256(scanned).hexdigest(),
                "byte_size": len(scanned), "verdict": "stream: OK",
            }

    runtime.asset_scanner = CleanScanner()
    unconfirmed_scan = owner_client.post(
        f"/business-units/digital-products/assets/{asset_id}/scan",
        headers=headers, json={"confirm_owner_scan": False},
    )
    assert unconfirmed_scan.status_code == 422
    scanned = owner_client.post(
        f"/business-units/digital-products/assets/{asset_id}/scan",
        headers=headers, json={"confirm_owner_scan": True},
    )
    assert scanned.status_code == 200
    assert scanned.json()["scan_status"] == "clean"
    assert scanned.json()["delivery_approval_required"] is True
    assert scanned.json()["download_enabled"] is False
    after_scan = owner_client.get(
        "/business-units/digital-products/assets", headers=headers
    ).json()["assets"][0]
    assert after_scan["storage_state"] == "private_scanned_clean"
    assert after_scan["status"] == "pending_delivery_approval"
    scan_events = owner_client.get(
        f"/business-units/digital-products/assets/{asset_id}/scan-events",
        headers=headers,
    )
    assert scan_events.status_code == 200
    assert scan_events.json()["count"] == 1
    assert scan_events.json()["events"][0]["status"] == "clean"

    duplicate = owner_client.put(
        f"/business-units/digital-products/assets/{asset_id}/content",
        headers={**headers, "Content-Type": "model/gltf-binary", "X-Confirm-Owner-Upload": "true"},
        content=payload_bytes,
    )
    assert duplicate.status_code == 409
    assert owner_client.get(
        f"/business-units/physical-agency/assets/{asset_id}/events", headers=headers
    ).status_code == 404


def test_business_asset_upload_rejects_corrupt_bytes(owner_client, tmp_path):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    expected = b"correct bytes"
    declared = owner_client.post("/business-units/physical-agency/assets", headers=headers, json={
        "asset_key": "checksum-test", "title": "Checksum test", "asset_type": "document",
        "filename": "notes.txt", "media_type": "text/plain",
        "checksum_sha256": hashlib.sha256(expected).hexdigest(), "byte_size": len(expected),
        "source": "owner upload", "confirm_owner_declaration": True,
    })
    asset_id = declared.json()["asset"]["asset_id"]
    runtime.asset_storage = PrivateFilesystemAssetStorage(tmp_path / "private-assets")
    response = owner_client.put(
        f"/business-units/physical-agency/assets/{asset_id}/content",
        headers={**headers, "Content-Type": "text/plain", "X-Confirm-Owner-Upload": "true"},
        content=b"tampered bytes",
    )
    assert response.status_code == 422
    assert "checksum" in response.json()["detail"].lower()
    assert owner_client.get("/business-units/physical-agency/assets", headers=headers).json()["assets"][0]["status"] == "pending_storage"

def test_business_asset_api_is_owner_confirmed_and_metadata_only(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    payload = {
        "asset_key": "hero-model", "title": "Hero model", "asset_type": "3d-model",
        "filename": "hero.glb", "media_type": "model/gltf-binary",
        "checksum_sha256": "a" * 64, "byte_size": 1024,
        "source": "owner asset manifest", "confirm_owner_declaration": True,
    }
    unauthenticated = owner_client.post("/business-units/physical-agency/assets", json=payload)
    assert unauthenticated.status_code == 401
    unconfirmed = owner_client.post(
        "/business-units/physical-agency/assets", headers=headers,
        json={**payload, "confirm_owner_declaration": False},
    )
    assert unconfirmed.status_code == 422
    declared = owner_client.post("/business-units/physical-agency/assets", headers=headers, json=payload)
    assert declared.status_code == 200
    result = declared.json()
    assert result["file_bytes_received"] is False
    assert result["asset"]["storage_state"] == "metadata_only"
    assert "No file was uploaded" in result["message"]
    asset_id = result["asset"]["asset_id"]
    listed = owner_client.get("/business-units/physical-agency/assets", headers=headers)
    assert listed.status_code == 200 and listed.json()["count"] == 1
    isolated = owner_client.get("/business-units/physical-brand/assets", headers=headers)
    assert isolated.status_code == 200 and isolated.json()["count"] == 0
    events = owner_client.get(
        f"/business-units/physical-agency/assets/{asset_id}/events", headers=headers
    )
    assert events.status_code == 200 and len(events.json()["events"]) == 1


def test_gateway_worker_executor_creates_owner_reviewable_draft_only():
    runtime = create_runtime(":memory:")
    agent_id = uuid4()
    role_key = "market_intelligence_analyst"
    runtime.agents[role_key] = {
        "id": str(agent_id), "role_key": role_key, "title": "Market Intelligence Analyst",
        "state": "active", "capabilities": ["market research", "competitor analysis"],
    }

    class FreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            assert request_budget_usd == 0.0
            return (object(),)

        def generate(self, request, *, request_budget_usd=0.0):
            assert request_budget_usd == 0.0
            assert request["task"] == "owner_approved_work_item_draft"
            assert "Do not contact customers" in request["prompt"]
            return ModelResult(
                text="## Research draft\\nEvidence and assumptions for owner review.",
                provider="test-free", model="test-model", cost_usd=0.0,
            )

    runtime.gateway = FreeGateway()
    item = WorkItem(
        id=uuid4(), title="Research competitors", objective="Prepare a competitor comparison.",
        department="Marketing", state=TaskState.READY, business_id="digital-products",
        assigned_agent_id=agent_id, assigned_role_key=role_key,
    )
    deliverable = runtime.worker.executor.execute(role_key, item)
    assert deliverable.work_item_id == item.id
    assert deliverable.role_key == role_key
    assert deliverable.provider == "test-free"
    assert deliverable.cost_usd == 0.0
    assert "owner review" in deliverable.content
    runtime.close()


def test_gateway_worker_executor_rejects_inactive_specialist():
    runtime = create_runtime(":memory:")
    agent_id = uuid4()
    role_key = "market_intelligence_analyst"
    runtime.agents[role_key] = {
        "id": str(agent_id), "role_key": role_key, "title": "Market Intelligence Analyst",
        "state": "draft", "capabilities": ["market research"],
    }
    item = WorkItem(
        id=uuid4(), title="Research competitors", objective="Prepare a competitor comparison.",
        department="Marketing", state=TaskState.READY, business_id="digital-products",
        assigned_agent_id=agent_id, assigned_role_key=role_key,
    )
    with pytest.raises(ValueError, match="not active"):
        runtime.worker.executor.execute(role_key, item)
    runtime.close()


def test_owner_run_once_executes_one_zero_cost_specialist_draft(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    agent_id = uuid4()
    role_key = "market_intelligence_analyst"
    runtime.agents[role_key] = {
        "id": str(agent_id), "role_key": role_key, "title": "Market Intelligence Analyst",
        "state": "active", "capabilities": ["market research", "competitor analysis"],
    }

    class FreeGateway:
        def eligible_providers(self, *, request_budget_usd=0.0):
            return (object(),) if request_budget_usd == 0.0 else ()

        def generate(self, request, *, request_budget_usd=0.0):
            assert request_budget_usd == 0.0
            return ModelResult(
                text="## Draft\\nOwner review required.",
                provider="test-free", model="test-model", cost_usd=0.0,
            )

    runtime.gateway = FreeGateway()
    item = WorkItem(
        id=uuid4(), title="Research a market", objective="Prepare a first-pass market analysis.",
        department="Marketing", state=TaskState.READY, business_id="digital-products",
        assigned_agent_id=agent_id, assigned_role_key=role_key,
    )
    audit = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="owner.created", subject_type="work_item",
        subject_id=str(item.id), outcome="recorded", correlation_id=str(uuid4()),
    )
    runtime.store.create_work_item(item, audit)
    runtime.queue.admit(item.id, agent_id, role_key)
    runtime.fleet.start()

    response = owner_client.post(
        "/workers/run-once", headers=headers,
        json={"agent_id": str(agent_id), "role_key": role_key},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed_review_required"
    assert response.json()["execution_mode"] == "single_task_owner_triggered"
    assert response.json()["background_loop_enabled"] is False
    assert runtime.store.get_work_item(item.id).state == TaskState.REVIEW
    assert runtime.queue.counts().get("done") == 1


def test_agent_registry_persists_profiles_and_owner_state_across_runtime_restart(tmp_path):
    database = tmp_path / "agent-registry.sqlite3"
    first = create_runtime(str(database))
    profile = {
        "id": str(uuid4()), "role_key": "intelligence-research__market_researcher",
        "name": "Market Researcher", "title": "Market Researcher",
        "department": "intelligence-research", "team_key": "intelligence-research__team_01",
        "capabilities": ["market research"], "state": "draft", "revision": 1,
        "kind": "specialist",
    }
    created = first.agents.setdefault(profile["role_key"], profile)
    created["state"] = "active"
    created["revision"] += 1
    first.agents.save(created)
    first.close()

    restarted = create_runtime(str(database))
    restored = restarted.agents.get(profile["role_key"])
    assert restored["id"] == profile["id"]
    assert restored["state"] == "active"
    assert restored["revision"] == 2
    assert len(restarted.agents.values()) == 1
    restarted.close()



def test_worker_service_status_is_owner_authenticated_and_reports_heartbeat(owner_client):
    unauthorized = owner_client.get("/workers/service-status")
    assert unauthorized.status_code == 401
    runtime = app.dependency_overrides[get_runtime]()
    worker_id = str(uuid4())
    runtime.worker_presence.start(worker_id)
    assert runtime.worker_presence.heartbeat(worker_id, 3) is True
    response = owner_client.get(
        "/workers/service-status",
        headers={"X-OpenCompany-API-Key": "test-owner-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["single_instance_mode"] is True
    assert payload["multi_replica_supported"] is False
    assert payload["worker_instances"][0]["worker_id"] == worker_id
    assert payload["worker_instances"][0]["processed_count"] == 3
    assert payload["worker_instances"][0]["stale"] is False


def test_owner_cannot_mark_or_queue_parent_work_before_prerequisites_complete(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    runtime = app.dependency_overrides[get_runtime]()
    specialist_id = uuid4()
    role_key = "intelligence-research__market_researcher"
    runtime.agents[role_key] = {
        "id": str(specialist_id), "role_key": role_key, "title": "Market Researcher",
        "kind": "specialist", "state": "active", "capabilities": ["research"],
    }
    prerequisite = WorkItem(
        id=uuid4(), title="Unfinished research", objective="Collect source evidence.",
        department="intelligence-research", state=TaskState.READY,
        business_id="digital-products",
    )
    parent = WorkItem(
        id=uuid4(), title="Management synthesis", objective="Synthesize the research.",
        department="intelligence-research", state=TaskState.DRAFT,
        business_id="digital-products", depends_on=(prerequisite.id,),
        assigned_agent_id=specialist_id, assigned_role_key=role_key,
    )
    runtime.store.create_work_item(prerequisite)
    runtime.store.create_work_item(parent)

    transition = owner_client.post(
        f"/work-items/{parent.id}/transition",
        headers=headers,
        json={"target_state": "ready"},
    )
    assert transition.status_code == 409
    assert "prerequisite" in transition.json()["detail"].lower()

    from dataclasses import replace
    ready_parent = replace(parent, state=TaskState.READY)
    audit = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_type="owner",
        actor_id="owner", action="test.force_ready", subject_type="work_item",
        subject_id=str(parent.id), outcome="recorded", correlation_id=str(uuid4()),
    )
    runtime.store.save_work_item_with_audit(ready_parent, audit)
    enqueue = owner_client.post(
        f"/work-items/{parent.id}/enqueue",
        headers=headers,
    )
    assert enqueue.status_code == 409
    assert "prerequisite" in enqueue.json()["detail"].lower()
    assert runtime.queue.counts().get("queued", 0) == 0


def test_finance_budget_status_and_statement_reconciliation_are_business_scoped(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    entry_base = {
        "business_id": "physical-agency", "currency": "USD",
        "confirm_owner_record": True,
    }
    revenue = owner_client.post("/finance/entries", headers=headers, json={
        **entry_base, "entry_type": "revenue", "amount_minor": 5000,
        "description": "Test customer receipt recorded, not payment initiated",
    })
    expense = owner_client.post("/finance/entries", headers=headers, json={
        **entry_base, "entry_type": "expense", "amount_minor": 1000,
        "description": "Test supplier cost recorded, not paid",
    })
    assert revenue.status_code == 200 and expense.status_code == 200

    budget = owner_client.post("/finance/budgets", headers=headers, json={
        "business_id": "physical-agency", "currency": "USD",
        "monthly_expense_limit_minor": 2000, "rationale": "Keep monthly operating expenses below the owner-approved cap.", "confirm_owner_budget": True,
    })
    assert budget.status_code == 200
    assert budget.json()["spending_authorized"] is False
    budget_history = owner_client.get("/finance/budgets/history?business_id=physical-agency", headers=headers)
    assert budget_history.status_code == 200
    assert budget_history.json()["count"] == 1
    assert budget_history.json()["events"][0]["rationale"].startswith("Keep monthly")

    status = owner_client.get(
        "/finance/budgets/status?business_id=physical-agency&currency=USD",
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["expenses_minor"] == 1000
    assert status.json()["revenue_minor"] == 5000
    assert status.json()["remaining_budget_minor"] == 1000
    assert status.json()["budget_status"] == "within_limit"

    start = "2026-11-01T00:00:00+00:00"
    end = "2026-11-30T23:59:59+00:00"
    reconciled = owner_client.post("/finance/reconciliations", headers=headers, json={
        "business_id": "physical-agency", "currency": "USD",
        "period_start": start, "period_end": end,
        "opening_balance_minor": 10000, "statement_closing_minor": 14000,
        "confirm_owner_reconciliation": True,
    })
    assert reconciled.status_code == 200
    assert reconciled.json()["ledger_movement_minor"] == 4000
    assert reconciled.json()["difference_minor"] == 0
    assert reconciled.json()["status"] == "balanced"
    assert reconciled.json()["funds_moved"] is False

    discrepancy = owner_client.post("/finance/reconciliations", headers=headers, json={
        "business_id": "physical-agency", "currency": "USD",
        "period_start": start, "period_end": end,
        "opening_balance_minor": 10000, "statement_closing_minor": 14500,
        "confirm_owner_reconciliation": True,
    })
    assert discrepancy.status_code == 200
    assert discrepancy.json()["difference_minor"] == 500
    assert discrepancy.json()["status"] == "discrepancy"

    isolated = owner_client.get(
        "/finance/budgets?business_id=physical-brand", headers=headers,
    )
    assert isolated.status_code == 200 and isolated.json()["count"] == 0
    history = owner_client.get(
        "/finance/reconciliations?business_id=physical-agency", headers=headers,
    )
    assert history.status_code == 200 and history.json()["count"] == 2


def test_business_integration_owner_review_is_audited_and_never_connects(owner_client, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-business-credential-encryption-key-32")
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    credential = owner_client.post(
        "/business-units/digital-products/credentials", headers=headers,
        json={"credential_key": "store-readonly", "secret": {"token": "not-returned"},
              "confirm_owner_storage": True},
    )
    assert credential.status_code == 200
    registered = owner_client.post(
        "/business-units/digital-products/integrations", headers=headers,
        json={"provider_key": "store-api", "display_name": "Digital Store",
              "credential_key": "store-readonly", "permissions": ["products:read"],
              "rationale": "Read-only product catalogue sync review",
              "confirm_owner_registration": True},
    )
    assert registered.status_code == 200
    integration_id = registered.json()["integration"]["integration_id"]
    unconfirmed = owner_client.post(
        f"/business-units/digital-products/integrations/{integration_id}/review",
        headers=headers, json={"decision": "approve", "rationale": "Reviewed"},
    )
    assert unconfirmed.status_code == 422
    approved = owner_client.post(
        f"/business-units/digital-products/integrations/{integration_id}/review",
        headers=headers, json={"decision": "approve", "rationale": "Read-only scope verified.",
                               "confirm_owner_decision": True},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved_pending_connection"
    assert approved.json()["external_connection_attempted"] is False
    duplicate = owner_client.post(
        f"/business-units/digital-products/integrations/{integration_id}/review",
        headers=headers, json={"decision": "reject", "rationale": "Duplicate decision",
                               "confirm_owner_decision": True},
    )
    assert duplicate.status_code == 409
    events = owner_client.get(
        f"/business-units/digital-products/integrations/{integration_id}/events",
        headers=headers,
    )
    assert [event["action"] for event in events.json()["events"]] == ["registered", "owner_approve"]


def test_ceo_coordination_cycle_runs_safe_phases_without_provider_or_queue_side_effects(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    bootstrapped = owner_client.post("/agents/bootstrap-executive", headers=headers)
    assert bootstrapped.status_code == 200
    agent = bootstrapped.json()["agent"]
    activated = owner_client.post(
        f"/agents/{agent['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": agent["revision"]},
    )
    assert activated.status_code == 200

    result = owner_client.post(
        "/executive/orchestration/cycle", headers=headers,
        json={"business_id": "digital-products"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["plan"] is None
    assert body["delegations"]["drafted_count"] == 0
    assert body["delegations"]["skipped"][0]["reason"] == "no_confirmed_zero_cost_provider"
    assert body["readiness"]["advanced_count"] == 0
    assert body["owner_approval_required_for_delegations"] is True
    assert body["queue_admission_performed"] is False
    assert body["execution_started"] is False
    assert body["parallel_execution_enabled"] is False


def test_ceo_coordination_cycle_requires_both_plan_title_and_objective(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    bootstrapped = owner_client.post("/agents/bootstrap-executive", headers=headers)
    agent = bootstrapped.json()["agent"]
    owner_client.post(
        f"/agents/{agent['id']}/state", headers=headers,
        json={"target_state": "active", "expected_revision": agent["revision"]},
    )
    result = owner_client.post(
        "/executive/orchestration/cycle", headers=headers,
        json={"title": "Incomplete request"},
    )
    assert result.status_code == 422


def test_business_unit_product_supplier_customer_and_order_workflow_is_internal_and_isolated(owner_client):
    headers = {"X-OpenCompany-API-Key": "test-owner-key"}
    supplier = owner_client.post(
        "/business-units/physical-agency/counterparties", headers=headers,
        json={"kind": "supplier", "name": "Synthetic Supplier", "country": "Pakistan",
              "reference": "supplier-test-record", "confirm_owner_record": True},
    )
    customer = owner_client.post(
        "/business-units/physical-agency/counterparties", headers=headers,
        json={"kind": "customer", "name": "Synthetic Buyer", "country": "United Kingdom",
              "reference": "buyer-test-record", "confirm_owner_record": True},
    )
    assert supplier.status_code == 200 and customer.status_code == 200

    product = owner_client.post(
        "/business-units/physical-agency/products", headers=headers,
        json={"sku": "SALT-TEST-01", "name": "Test Salt Pack",
              "description": "Synthetic test product record.", "unit_price_minor": 2500,
              "currency": "USD", "supplier_id": supplier.json()["id"],
              "confirm_owner_product": True},
    )
    assert product.status_code == 200
    assert product.json()["status"] == "draft"
    assert product.json()["published_externally"] is False
    product_id = product.json()["id"]

    not_active = owner_client.post(
        "/business-units/physical-agency/orders", headers=headers,
        json={"customer_id": customer.json()["id"], "currency": "USD",
              "items": [{"product_id": product_id, "quantity": 2}],
              "confirm_owner_order": True},
    )
    assert not_active.status_code == 422

    activated = owner_client.post(
        f"/business-units/physical-agency/products/{product_id}/activate",
        headers=headers,
        json={"confirm_owner_decision": True, "rationale": "Approved for internal order drafting."},
    )
    assert activated.status_code == 200
    assert activated.json()["published_externally"] is False

    order = owner_client.post(
        "/business-units/physical-agency/orders", headers=headers,
        json={"customer_id": customer.json()["id"], "currency": "USD",
              "items": [{"product_id": product_id, "quantity": 2}],
              "confirm_owner_order": True},
    )
    assert order.status_code == 200
    body = order.json()
    assert body["total_minor"] == 5000
    assert body["status"] == "draft"
    assert body["customer_contacted"] is False
    order_id = body["id"]

    transitions = [
        ("owner_approved", {"confirm_owner_decision": True, "rationale": "Owner approved internal order record."}),
        ("awaiting_payment_verification", {"confirm_owner_decision": True, "rationale": "Awaiting evidence review."}),
        ("payment_verified_owner_attested", {"confirm_owner_decision": True, "confirm_payment_verification": True,
                                              "rationale": "Owner reviewed supplied receipt reference.",
                                              "evidence_reference": "synthetic-receipt-001"}),
        ("fulfilling", {"confirm_owner_decision": True, "rationale": "Internal fulfillment coordination started."}),
        ("fulfilled", {"confirm_owner_decision": True, "rationale": "Owner recorded fulfillment completion."}),
    ]
    for target, extra in transitions:
        result = owner_client.post(
            f"/business-units/physical-agency/orders/{order_id}/transition",
            headers=headers, json={"target_status": target, **extra},
        )
        assert result.status_code == 200
        assert result.json()["status"] == target
        assert result.json()["external_customer_contact"] is False
        assert result.json()["funds_moved"] is False
        assert result.json()["fulfillment_executed"] is False
    assert result.json()["payment_status_independently_verified"] is False

    isolated = owner_client.get("/business-units/physical-brand/orders", headers=headers)
    assert isolated.status_code == 200 and isolated.json()["count"] == 0
    cross_business = owner_client.post(
        "/business-units/digital-products/orders", headers=headers,
        json={"customer_id": customer.json()["id"], "currency": "USD",
              "items": [{"product_id": product_id, "quantity": 1}],
              "confirm_owner_order": True},
    )
    assert cross_business.status_code == 422


def test_treasury_owner_api_registers_accounts_and_lists_only_selected_business(owner_client):
    headers={"X-OpenCompany-API-Key":"test-owner-key"}
    response=owner_client.post("/treasury/accounts",headers=headers,json={
        "owner_confirmed":True,"business_id":"digital-products","name":"Operating cash",
        "currency":"USD","account_type":"cash","masked_reference":"***4321"})
    assert response.status_code==200
    assert response.json()["status"]=="record_only"
    listed=owner_client.get("/treasury/accounts/digital-products",headers=headers)
    assert listed.status_code==200
    assert len(listed.json()["accounts"])==1
    assert listed.json()["live_provider_balance_available"] is False
    other=owner_client.get("/treasury/accounts/physical-brand",headers=headers)
    assert other.json()["accounts"]==[]

def test_treasury_api_requires_owner_confirmation_and_authentication(owner_client):
    headers={"X-OpenCompany-API-Key":"test-owner-key"}
    missing_confirmation=owner_client.post("/treasury/accounts",headers=headers,json={
        "business_id":"physical-brand","name":"Cash","currency":"PKR"})
    assert missing_confirmation.status_code==400
    unauthenticated=owner_client.get("/treasury/accounts/physical-brand")
    assert unauthenticated.status_code==401

def test_treasury_spend_request_approval_never_moves_money(owner_client):
    headers={"X-OpenCompany-API-Key":"test-owner-key"}
    request=owner_client.post("/treasury/spend-requests",headers=headers,json={
        "owner_confirmed":True,"business_id":"physical-agency","requester_id":"marketing-agent",
        "payee":"Supplier","purpose":"Sample expense","amount_minor":250000,
        "currency":"PKR","budget_category":"marketing"})
    assert request.status_code==200
    request_id=request.json()["id"]
    decision=owner_client.post(f"/treasury/spend-requests/physical-agency/{request_id}/decision",
        headers=headers,json={"approve":True,"note":"Approved for planning only"})
    assert decision.status_code==200
    assert decision.json()["status"]=="approved"
    assert decision.json()["payment_executed"] is False
    assert decision.json()["funds_moved"] is False


def test_agent_workspace_reports_profile_separately_from_real_worker_activity(owner_client):
    headers={"X-OpenCompany-API-Key":"test-owner-key"}
    boot=owner_client.post("/agents/bootstrap-executive",headers=headers)
    assert boot.status_code==200
    agent_id=boot.json()["agent"]["id"]
    response=owner_client.get(f"/agents/{agent_id}/workspace",headers=headers)
    assert response.status_code==200
    payload=response.json()
    assert payload["agent"]["id"]==agent_id
    assert payload["live"]["execution_status"]=="not_provisioned"
    assert payload["live"]["active_work_count"]==0
    assert payload["live"]["worker_instances"]==[]
    assert payload["prompt"]["source"]=="OpenCompany first-party role catalogue"
    assert payload["workspace_sections"]["messages"]=="not_implemented"
    assert payload["workspace_sections"]["agent_memory"]=="available"
    assert payload["agent_memory"]==[]


def test_agent_workspace_is_owner_authenticated_and_rejects_unknown_agent(owner_client):
    headers={"X-OpenCompany-API-Key":"test-owner-key"}
    assert owner_client.get("/agents/missing/workspace").status_code==401
    assert owner_client.get("/agents/missing/workspace",headers=headers).status_code==404


def test_agent_workspace_exposes_only_approved_private_agent_memory(owner_client):
    headers={"X-OpenCompany-API-Key":"test-owner-key"}
    boot=owner_client.post("/agents/bootstrap-executive",headers=headers)
    assert boot.status_code==200
    agent_id=boot.json()["agent"]["id"]
    runtime=app.dependency_overrides[get_runtime]()

    approved=runtime.brain_memory.propose(
        f"agent:{agent_id}","Research standard",
        "Verify claims against independent evidence","owner",confidence=0.95,
    )
    runtime.brain_memory.review(approved["id"],True,"Owner approved")
    pending=runtime.brain_memory.propose(
        f"agent:{agent_id}","Unreviewed note",
        "Treat this unverified claim as fact","agent",confidence=0.99,
    )

    response=owner_client.get(f"/agents/{agent_id}/workspace",headers=headers)
    assert response.status_code==200
    payload=response.json()
    assert payload["workspace_sections"]["agent_memory"]=="available"
    assert [item["id"] for item in payload["agent_memory"]]==[approved["id"]]
    assert pending["id"] not in {item["id"] for item in payload["agent_memory"]}
